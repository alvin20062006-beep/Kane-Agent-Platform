import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, access, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = await mkdtemp(path.join(tmpdir(), "kane-ui-e2e-"));
const apiPort = Number(process.env.UI_TEST_API_PORT ?? 8100);
const webPort = Number(process.env.UI_TEST_WEB_PORT ?? 3100);
const apiBase = `http://127.0.0.1:${apiPort}`;
const webBase = `http://127.0.0.1:${webPort}`;
const token = "kane-ui-test-only";
const children = [];
const results = [];
let browser;
let page;
let backend;
let stage = "startup";
const pageErrors = [];
const badResponses = [];
const consoleErrors = [];

async function poll(read, test = Boolean, timeout = 20000) {
  const started = Date.now();
  let value;
  while (Date.now() - started < timeout) {
    value = await read();
    if (test(value)) return value;
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  throw new Error(`Timed out in ${stage}: ${JSON.stringify(value)}`);
}

async function available(port) {
  const { createServer } = await import("node:net");
  await new Promise((resolve, reject) => { const server = createServer(); server.once("error", reject); server.listen(port, "127.0.0.1", () => server.close(resolve)); });
}

function start(command, args, cwd, env) {
  const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  child.log = "";
  for (const stream of [child.stdout, child.stderr]) stream.on("data", data => { child.log = (child.log + data.toString()).slice(-12000); });
  child.on("error", error => { child.log += error.message; });
  children.push(child);
  return child;
}

async function stop(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  let diagnostic = "";
  if (process.platform === "win32") {
    const result = spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, encoding: "utf8" });
    diagnostic = result.stderr || result.error?.message || "";
  } else child.kill("SIGTERM");
  // A descendant may exit during taskkill; require actual child exit, then check ports.
  try { await poll(() => child.exitCode !== null || child.signalCode !== null, Boolean, 10000); }
  catch { throw new Error(`Cannot stop owned test process ${child.pid}: ${diagnostic}`); }
}

async function apiGet(endpoint) {
  const response = await fetch(`${apiBase}${endpoint}`, { headers: { "X-Api-Key": token } });
  assert.equal(response.status, 200, `${endpoint}: ${response.status}`);
  return response.json();
}

async function ready(url, child) {
  await poll(async () => {
    if (child.exitCode !== null) throw new Error(child.log);
    try { return (await fetch(url, { signal: AbortSignal.timeout(1500) })).ok; } catch { return false; }
  }, Boolean, 90000);
}

let python = process.platform === "win32" ? path.join(root, "apps/api/.venv/Scripts/python.exe") : path.join(root, "apps/api/.venv/bin/python");
try { await access(python); } catch { python = process.env.PYTHON ?? "python"; }
function startApi() {
  return start(python, ["-m", "uvicorn", "ui_fixture_current:create_ui_app", "--factory", "--app-dir", output, "--host", "127.0.0.1", "--port", String(apiPort)], path.join(root, "apps/api"), { KANE_UI_TEST: "1", KANE_SQLITE_PATH: path.join(output, "kane.db"), OCTOPUS_API_TOKEN: token, PYTHONPATH: path.join(root, "apps/api"), PYTHONDONTWRITEBYTECODE: "1" });
}

try {
  // Adapt only the legacy test peer's completion frame; frozen backend files stay untouched.
  const fixture = await readFile(path.join(root, "apps/api/tests/ui_fixture.py"), "utf8");
  await writeFile(path.join(output, "ui_fixture_current.py"), fixture.replace('"stopReason": "endTurn"', '"stopReason": "end_turn", "_meta": {"kaneNativeEndKind": "completed"}'));
  await available(apiPort); await available(webPort);
  backend = startApi();
  const web = start(process.execPath, [path.join(root, "node_modules/next/dist/bin/next"), "dev", "--webpack", "--hostname", "127.0.0.1", "--port", String(webPort)], path.join(root, "apps/web"), { KANE_API_BASE_URL: apiBase, OCTOPUS_API_TOKEN: token, NEXT_TELEMETRY_DISABLED: "1" });
  await ready(`${apiBase}/health`, backend); await ready(webBase, web);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  await context.addInitScript(() => { if (!localStorage.getItem("kane.locale")) localStorage.setItem("kane.locale", "en"); });
  await context.addInitScript(value => sessionStorage.setItem("kane.apiAccessToken", value), token);
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", error => pageErrors.push({ stage, message: error.message }));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push({ stage, message: message.text() }); });
  page.on("response", response => { if (response.url().startsWith(webBase) && response.status() >= 400) badResponses.push({ stage, url: response.url(), status: response.status() }); });
  const bodies = [];
  page.on("request", request => { if (request.method() === "POST") bodies.push({ url: request.url(), body: request.postDataJSON() }); });

  async function check(name, run) { stage = name; const started = Date.now(); await run(); results.push({ name, status: "PASS", ms: Date.now() - started }); console.log(`PASS ${name}`); }
  const currentId = () => new URL(page.url()).searchParams.get("conversation");
  const currentTurn = () => new URL(page.url()).searchParams.get("turn");
  const waitStatus = status => poll(async () => currentTurn() ? (await apiGet(`/api/v1/turns/${currentTurn()}`)).status : null, value => value === status);
  async function send(text) { await page.getByRole("textbox", { name: "Message", exact: true }).fill(text); await page.getByRole("button", { name: "Send", exact: true }).click(); await poll(() => currentTurn()); }
  async function newTask(name) { await page.locator(".composer-region").getByRole("button", { name: "New task", exact: true }).click(); const modal = page.getByRole("dialog"); await modal.getByRole("textbox", { name: "Task title" }).fill(name); await modal.getByRole("button", { name: "Create task", exact: true }).click(); await modal.waitFor({ state: "hidden" }); await poll(async () => currentTurn() ? (await apiGet(`/api/v1/turns/${currentTurn()}`)).title : null, value => value === name); }
  async function screenshot(name) { await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: false, animations: "disabled" }); }

  await check("Web proxy requires caller token and checks mutation origin", async () => {
    const target = `${webBase}/api/proxy/api/v1/conversations`;
    assert.equal((await fetch(target)).status, 401);
    assert.equal((await fetch(target, { headers: { "X-Api-Key": "wrong" } })).status, 401);
    assert.equal((await fetch(target, { headers: { "X-Api-Key": token } })).status, 200);
    assert.equal((await fetch(target, { method: "DELETE", headers: { "X-Api-Key": token, Origin: "https://attacker.example" } })).status, 403);
    const unauthenticated = await browser.newContext();
    await unauthenticated.addInitScript(() => localStorage.setItem("kane.locale", "en"));
    const loginPage = await unauthenticated.newPage();
    try {
      await loginPage.goto(webBase, { waitUntil: "domcontentloaded" });
      const dialog = loginPage.getByRole("dialog", { name: "Connect to Kane API" });
      await dialog.getByLabel("API access token").fill(token);
      await dialog.getByRole("button", { name: "Connect", exact: true }).click();
      await dialog.waitFor({ state: "hidden" });
    } finally { await unauthenticated.close(); }
  });

  await check("three-field model form / existing HTTP contract / no external page", async () => {
    await page.goto(webBase, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Kanaloa model and API settings", exact: true }).click();
    const modal = page.getByRole("dialog");
    await modal.getByRole("heading", { name: "Built-in Kanaloa API", exact: true }).waitFor();
    assert.equal(await modal.getByLabel("Model", { exact: true }).inputValue(), "");
    assert.equal(bodies.length, 0);
    await page.route("**/agents/kanaloa/model-config", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "saved", provider: "kane-kanaloa", model: "ui-contract-model" }) }));
    await modal.getByLabel("Base URL", { exact: true }).fill("https://api.example.com/v1");
    await modal.getByLabel("Model", { exact: true }).fill("ui-contract-model");
    await modal.getByLabel("API Key", { exact: true }).fill("ui-contract-placeholder");
    await modal.getByRole("button", { name: "Save model configuration", exact: true }).click();
    await modal.getByText("Model configuration saved for the built-in Kanaloa runtime.", { exact: true }).waitFor();
    assert.deepEqual(bodies.at(-1).body, { base_url: "https://api.example.com/v1", model: "ui-contract-model", api_key: "ui-contract-placeholder" });
    assert.equal(await modal.getByLabel("API Key", { exact: true }).inputValue(), "");
    assert.equal(context.pages().length, 1);
    await page.unroute("**/agents/kanaloa/model-config");
    await screenshot("agent-settings");
    await modal.getByRole("button", { name: "Close", exact: true }).click();
  });

  await check("empty / create conversation / registered agent", async () => {
    await page.goto(webBase, { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Start a conversation", exact: true }).click();
    const modal = page.getByRole("dialog");
    assert.equal(await modal.getByRole("combobox", { name: "Agent", exact: true }).locator("option").count(), 1);
    await modal.getByRole("textbox", { name: "Title", exact: true }).fill("Kane architecture review");
    await modal.getByRole("button", { name: "Create conversation", exact: true }).click();
    await page.locator(".conversation-header").getByText("Kane architecture review", { exact: true }).waitFor();
    assert.equal((await apiGet("/api/v1/conversations")).length, 1);
  });

  let firstMessage;
  let mainTurn;
  await check("pin preference / persisted rename / real delete", async () => {
    const cid = currentId();
    await page.getByRole("button", { name: "Conversation actions: Kane architecture review", exact: true }).click();
    await page.getByRole("menuitem", { name: "Pin", exact: true }).click();
    assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem("kane.conversation-pins"))), [cid]);
    await page.getByRole("button", { name: "Conversation actions: Kane architecture review", exact: true }).click();
    await page.getByRole("menuitem", { name: "Rename", exact: true }).click();
    await page.getByRole("dialog").getByLabel("Title", { exact: true }).fill("Renamed conversation");
    await page.getByRole("dialog").getByRole("button", { name: "Save name", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.equal((await apiGet(`/api/v1/conversations/${cid}`)).title, "Renamed conversation");
    await page.getByRole("button", { name: "Conversation actions: Renamed conversation", exact: true }).click();
    await page.getByRole("menuitem", { name: "Rename", exact: true }).click();
    await page.getByRole("dialog").getByLabel("Title", { exact: true }).fill("Kane architecture review");
    await page.getByRole("dialog").getByRole("button", { name: "Save name", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    await page.locator("#conversation-sidebar").getByRole("button", { name: "New conversation", exact: true }).click();
    await page.getByRole("dialog").getByLabel("Title", { exact: true }).fill("Delete me");
    await page.getByRole("dialog").getByRole("button", { name: "Create conversation", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    await poll(currentId, id => id !== cid);
    const removed = currentId();
    await page.getByRole("button", { name: "Conversation actions: Delete me", exact: true }).click();
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.ok(!(await apiGet("/api/v1/conversations")).some(item => item.conversation_id === removed));
    await page.locator(".conversation-row").filter({ hasText: "Kane architecture review" }).click();
    await poll(currentId, id => id === cid);
  });
  await check("first send / streaming / one logical message / safe events", async () => {
    await send("Review the Kane architecture and explain the conversation boundary.");
    assert.equal(bodies.filter(entry => entry.url.endsWith("/messages")).at(-1).body.loop_mode, undefined);
    await page.getByTestId("partial-reply").waitFor();
    await waitStatus("finished");
    await page.getByTestId("message-agent").waitFor();
    assert.equal(await page.getByTestId("message-agent").count(), 1);
    await page.getByTestId("partial-reply").waitFor({ state: "hidden" });
    const history = await apiGet(`/api/v1/conversations/${currentId()}/messages`);
    firstMessage = history[0].message_id; mainTurn = currentTurn();
    assert.equal(history.length, 2);
    assert.ok(!(await page.locator("body").innerText()).includes("PRIVATE_CHAIN_OF_THOUGHT"));
    await screenshot("desktop-conversation");
  });

  let taskA, taskB;
  await check("New Task / send while running / native steer", async () => {
    await newTask("Adapter research"); taskA = currentTurn();
    await send("[hold] Study the adapter boundary.");
    await page.getByTestId("partial-reply").waitFor();
    await send("Focus on session continuity.");
    await poll(async () => (await apiGet("/__ui__/calls")).filter(call => call.method === "session/steer").length, count => count === 1);
    assert.equal((await apiGet(`/api/v1/turns/${taskA}`)).status, "running");
  });

  await check("parallel turns / inspect without focus / targeted send / explicit focus", async () => {
    await newTask("Recovery review"); taskB = currentTurn();
    await send("[hold] Review interruption recovery.");
    await page.getByTestId("partial-reply").waitFor();
    let turns = await apiGet(`/api/v1/conversations/${currentId()}/turns`);
    assert.equal(turns.filter(turn => turn.status === "running").length, 2);
    assert.notEqual(turns.find(turn => turn.turn_id === taskA).native_session_ref, turns.find(turn => turn.turn_id === taskB).native_session_ref);
    await page.getByRole("combobox", { name: "Current Turn", exact: true }).selectOption(taskA);
    await poll(currentTurn, tid => tid === taskA);
    assert.equal((await apiGet(`/api/v1/conversations/${currentId()}`)).focus_turn_id, taskB);
    await send("Keep this instruction with the adapter task.");
    const calls = await apiGet("/__ui__/calls");
    assert.equal(calls.filter(call => call.method === "session/steer").at(-1).params.sessionId, turns.find(turn => turn.turn_id === taskA).native_session_ref);
    await page.getByRole("button", { name: "Focus this task", exact: false }).click();
    await poll(async () => (await apiGet(`/api/v1/conversations/${currentId()}`)).focus_turn_id, tid => tid === taskA);
    await screenshot("desktop-parallel-turns");
  });

  await check("active conversation delete returns 409 / no implicit cancel", async () => {
    const cid = currentId();
    const before = (await apiGet("/__ui__/calls")).filter(call => call.method === "session/cancel").length;
    await page.getByRole("button", { name: "Conversation actions: Kane architecture review", exact: true }).click();
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("dialog").getByRole("alert").waitFor();
    assert.equal(badResponses.at(-1).status, 409);
    assert.equal((await apiGet(`/api/v1/conversations/${cid}`)).conversation_id, cid);
    assert.equal((await apiGet("/__ui__/calls")).filter(call => call.method === "session/cancel").length, before);
    await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
  });

  await check("branch from message / server history boundary / isolated session", async () => {
    await page.locator(`[data-message-id="${firstMessage}"]`).getByRole("button", { name: "Branch from here", exact: true }).click();
    const modal = page.getByRole("dialog");
    await modal.getByRole("textbox", { name: "Branch name" }).fill("Alternative approach");
    await modal.getByRole("button", { name: "Create branch", exact: true }).click();
    await modal.waitFor({ state: "hidden" });
    await page.getByText("Branch context", { exact: true }).waitFor();
    await poll(async () => page.locator("[data-message-id]").count(), count => count === 1);
    const history = await apiGet(`/api/v1/conversations/${currentId()}/messages?turn_id=${currentTurn()}`);
    assert.deepEqual(await page.locator("[data-message-id]").evaluateAll(nodes => nodes.map(node => node.dataset.messageId)), history.map(message => message.message_id));
    await send("Consider the alternative approach."); await waitStatus("finished");
    assert.notEqual((await apiGet(`/api/v1/turns/${mainTurn}`)).native_session_ref, (await apiGet(`/api/v1/turns/${currentTurn()}`)).native_session_ref);
  });

  await check("per-turn drafts survive inspection", async () => {
    const branch = currentTurn();
    const input = page.getByRole("textbox", { name: "Message", exact: true });
    await input.fill("Unsent branch instruction");
    await page.getByRole("button", { name: "Loop settings", exact: true }).click();
    await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).check();
    await page.getByRole("combobox", { name: "Iteration limit", exact: true }).selectOption("custom");
    await page.getByRole("spinbutton", { name: "Iterations", exact: true }).fill("7");
    await page.getByRole("combobox", { name: "Current Turn", exact: true }).selectOption(taskA);
    await poll(currentTurn, tid => tid === taskA);
    assert.equal(await input.inputValue(), "");
    await input.fill("Unsent adapter instruction");
    await page.getByRole("combobox", { name: "Current Turn", exact: true }).selectOption(branch);
    await poll(currentTurn, tid => tid === branch);
    assert.equal(await input.inputValue(), "Unsent branch instruction");
    await page.getByRole("button", { name: "Loop settings", exact: true }).click();
    assert.ok(await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).isChecked());
    assert.equal(await page.getByRole("combobox", { name: "Iteration limit", exact: true }).inputValue(), "custom");
    assert.equal(await page.getByRole("spinbutton", { name: "Iterations", exact: true }).inputValue(), "7");
    await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).uncheck();
    await input.fill("");
  });

  await check("approval survives refresh / allow once", async () => {
    await newTask("Review permission"); await send("[approval] Check the project files.");
    await page.getByRole("region", { name: "Approval required" }).waitFor();
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("region", { name: "Approval required" }).waitFor();
    await screenshot("desktop-approval");
    await page.getByRole("button", { name: "Allow once", exact: true }).click();
    await waitStatus("finished");
    assert.equal(bodies.filter(entry => entry.url.includes("/permissions/")).at(-1).body.decision, "allow-once");
  });

  for (const [label, decision] of [["Deny", "reject-once"], ["Cancel request", "cancelled"]]) {
    await check(`approval ${decision}`, async () => {
      await newTask(`Permission ${decision}`); await send("[approval] Confirm this test request.");
      await page.getByRole("button", { name: label, exact: true }).click();
      await waitStatus("finished");
      assert.equal(bodies.filter(entry => entry.url.includes("/permissions/")).at(-1).body.decision, decision);
    });
  }

  await check("stale approval reports the real backend rejection", async () => {
    await newTask("Stale permission"); await send("[approval] Resolve from another client.");
    await page.getByRole("button", { name: "Allow once", exact: true }).waitFor();
    await page.route("**/permissions/*/respond", async route => {
      // Another client wins the race; the UI must not claim its duplicate succeeded.
      const endpoint = new URL(route.request().url()).pathname.replace("/api/proxy", "");
      const first = await fetch(`${apiBase}${endpoint}`, { method: "POST", headers: { "X-Api-Key": token, "Content-Type": "application/json" }, body: route.request().postData() });
      assert.equal(first.status, 200);
      await route.continue();
    });
    await page.getByRole("button", { name: "Allow once", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "Unknown permission request" }).waitFor();
    assert.equal(badResponses.at(-1).status, 400);
    await page.unroute("**/permissions/*/respond");
  });

  await check("cancel / interrupted partial / truthful resume result", async () => {
    await newTask("Interrupt and resume"); await send("[hold] Keep partial output.");
    await page.getByTestId("partial-reply").waitFor();
    await page.locator(".composer-controls").getByRole("button", { name: "Cancel execution", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel execution", exact: true }).click();
    await waitStatus("interrupted");
    await page.getByText("Task interrupted", { exact: true }).waitFor();
    assert.ok((await page.getByTestId("partial-reply").innerText()).includes("I have reviewed"));
    await page.locator(".runtime-notice").getByRole("button", { name: "Resume", exact: true }).click();
    await poll(async () => (await apiGet(`/api/v1/turns/${currentTurn()}`)).interrupt_reason, reason => reason === "session_rebound:unfinished_work_not_resumed");
    assert.equal(bodies.filter(entry => entry.url.endsWith("/resume")).length, 1);
    assert.equal((await apiGet(`/api/v1/turns/${currentTurn()}`)).status, "interrupted");
    await page.getByText("session_rebound:unfinished_work_not_resumed", { exact: true }).waitFor();
  });

  await check("transport interruption / explicit failed presentation", async () => {
    await newTask("Transport interruption"); await send("[interrupt] Preserve this response."); await waitStatus("interrupted");
    await page.getByText("Task interrupted", { exact: true }).waitFor();
    await newTask("Explicit work failure"); await send("[failed] Report work failure."); await waitStatus("failed");
    await page.getByText("Task failed", { exact: true }).waitFor();
    assert.equal((await apiGet(`/api/v1/turns/${currentTurn()}`)).interrupt_reason, "agent_reported_failure");
  });

  for (const [mode, value] of [["default", 5], ["custom", 2], ["unlimited", null]]) {
    await check(`Loop ${mode} / HTTP parameter / runtime`, async () => {
      await newTask(`Loop ${mode}`);
      await page.getByRole("button", { name: "Loop settings", exact: true }).click();
      await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).check();
      await page.getByRole("combobox", { name: "Iteration limit", exact: true }).selectOption(mode);
      if (mode === "custom") {
        await page.getByRole("textbox", { name: "Message", exact: true }).fill("[loop] Check a work iteration.");
        for (const invalid of ["0", "-1", "1.5", "", "9007199254740992"]) {
          await page.getByRole("spinbutton", { name: "Iterations", exact: true }).fill(invalid);
          assert.ok(await page.getByRole("button", { name: "Send", exact: true }).isDisabled());
        }
        await page.getByRole("spinbutton", { name: "Iterations", exact: true }).fill("2");
      }
      await send("[loop] Check a work iteration.");
      const body = bodies.filter(entry => entry.url.endsWith("/messages")).at(-1).body;
      assert.equal(body.loop_mode, true); assert.equal(body.max_iterations, value);
      if (mode === "unlimited") {
        await page.locator(".composer-controls").getByRole("button", { name: "Stop loop", exact: true }).waitFor();
        assert.match(await page.locator(".composer-controls").textContent(), /Loop active.*∞/);
        assert.ok(await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).isDisabled());
        const cancels = bodies.filter(entry => entry.url.endsWith("/cancel")).length;
        await page.locator(".composer-controls").getByRole("button", { name: "Stop loop", exact: true }).click();
        assert.equal(bodies.filter(entry => entry.url.endsWith("/cancel")).length, cancels);
      }
      await waitStatus("finished");
      const history = await apiGet(`/api/v1/conversations/${currentId()}/messages?turn_id=${currentTurn()}`);
      const last = history.filter(message => message.turn_id === currentTurn() && message.sender === "agent");
      assert.equal(last.length, 1);
      if (value !== null) assert.equal((last[0].content.match(/Iteration \d+ checked/g) ?? []).length, value);
    });
  }

  await check("long reply remains one message", async () => {
    await newTask("Long response"); await send("[long] Return a long response."); await waitStatus("finished");
    const messages = await apiGet(`/api/v1/conversations/${currentId()}/messages`);
    const replies = messages.filter(message => message.turn_id === currentTurn() && message.sender === "agent");
    assert.equal(replies.length, 1); assert.ok(replies[0].content.length > 30000);
    await poll(() => page.locator(`[data-message-id="${replies[0].message_id}"] .message-content`).textContent(), text => text === replies[0].content);
  });

  await check("SSE reconnect / no cancel on refresh", async () => {
    await newTask("Reconnect observation");
    let aborted = false;
    await page.route("**/stream", async route => { if (!aborted) { aborted = true; await route.abort("connectionreset"); } else await route.continue(); });
    await send("[hold] Observe reconnect.");
    await poll(() => aborted);
    await page.getByTestId("stream-status").getByText("Connected", { exact: true }).waitFor();
    await page.unroute("**/stream");
    const before = (await apiGet("/__ui__/calls")).filter(call => call.method === "session/cancel").length;
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("partial-reply").waitFor();
    assert.equal((await apiGet("/__ui__/calls")).filter(call => call.method === "session/cancel").length, before);
    assert.equal((await apiGet(`/api/v1/turns/${currentTurn()}`)).status, "running");
  });

  await check("responsive desktop / tablet / mobile / drawer controls", async () => {
    for (const [width, height, name] of [[1280, 800, "laptop"], [900, 900, "tablet"], [390, 844, "mobile"]]) {
      await page.setViewportSize({ width, height }); await page.reload({ waitUntil: "domcontentloaded" });
      await page.getByRole("textbox", { name: "Message", exact: true }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} horizontal overflow`);
      if (width <= 700) {
        await page.getByRole("button", { name: "Open conversations", exact: true }).click();
        await page.keyboard.press("Shift+Tab");
        assert.ok(await page.evaluate(() => document.getElementById("conversation-sidebar").contains(document.activeElement)));
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Open work inspector", exact: true }).click();
        await page.getByRole("button", { name: "Hide work inspector", exact: true }).click();
      }
      await screenshot(name);
      await page.getByRole("button", { name: "Loop settings", exact: true }).click();
      await page.getByText("Loop settings are available before execution or on a follow-up.", { exact: true }).waitFor();
      assert.ok(await page.getByRole("checkbox", { name: "Use loop mode", exact: true }).isDisabled());
      await screenshot(`${name}-loop`);
      await page.getByRole("button", { name: "Loop settings", exact: true }).click();
      await page.getByRole("button", { name: "Kanaloa model and API settings", exact: true }).click();
      await page.getByRole("dialog").getByRole("heading", { name: "Built-in Kanaloa API", exact: true }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name} settings overflow`);
      await screenshot(`${name}-settings`);
      await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
      if (name === "mobile") {
        await page.evaluate(() => localStorage.setItem("kane.locale", "zh"));
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.getByRole("textbox", { name: "消息", exact: true }).waitFor();
        await page.getByRole("button", { name: "Kanaloa 模型与 API 配置", exact: true }).click();
        await page.getByRole("dialog").getByRole("heading", { name: "内置 Kanaloa API", exact: true }).waitFor();
        await screenshot("mobile-settings-zh");
        await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
        await page.evaluate(() => localStorage.setItem("kane.locale", "en"));
        await page.reload({ waitUntil: "domcontentloaded" });
      }
    }
    await page.setViewportSize({ width: 1440, height: 960 });
  });

  await check("pairing / Skill-MCP bootstrap / truthful online and disconnect", async () => {
    await page.getByRole("button", { name: "Connect an external Agent", exact: true }).click();
    const modal = page.getByRole("dialog");
    await modal.getByLabel("Agent ID", { exact: true }).fill("ui-protocol-peer");
    await modal.getByLabel("Display name", { exact: true }).fill("UI Protocol Peer");
    const response = page.waitForResponse(res => res.url().endsWith("/agents/pairings") && res.request().method() === "POST");
    await modal.getByRole("button", { name: "Create pairing code", exact: true }).click();
    const pairing = await (await response).json();
    assert.equal(pairing.expires_in_seconds, null);
    await modal.getByText("Waiting for Agent Connector", { exact: true }).waitFor();
    assert.equal((await apiGet("/api/v1/agents")).find(agent => agent.agent_id === pairing.agent_id).status, "unavailable");
    await modal.getByLabel("Kane repository on the Agent host", { exact: true }).fill("C:/Kane");
    const config = JSON.parse(await modal.locator(".setup-command").innerText());
    assert.equal(config.mcpServers.kane.env.KANE_CONNECTOR_WS_URL, `ws://127.0.0.1:${apiPort}/api/v1/connectors/ws`);
    assert.equal(config.mcpServers.kane.env.KANE_AGENT_ID, pairing.agent_id);
    assert.equal(config.mcpServers.kane.args[0], "C:/Kane/connectors/kane-mcp/server.py");
    assert.ok(!JSON.stringify(config).includes(pairing.pairing_code));
    assert.ok(!(await modal.innerText()).includes("expires"));
    const peer = spawn(python, ["-c", `import asyncio,json,sys,websockets\nasync def main():\n data=json.loads(sys.stdin.readline())\n async with websockets.connect(data['url'],additional_headers={'Authorization':'Pairing '+data['code']}) as ws:\n  await ws.send(json.dumps({'protocol':'kane-connector','version':'0.1','type':'connector.hello','id':'ui-hello','payload':{'agent_id':'ui-protocol-peer','connector_id':'ui-peer','capabilities':{'supports_stream':True,'supports_resume':False,'supports_cancel':False,'supports_approval':False,'supports_parallel_sessions':False,'max_parallel_sessions':None,'steer_mode':'follow_up_only','branch_mode':'unsupported'},'sessions':[]}}))\n  await ws.recv()\n  await asyncio.sleep(20)\nasyncio.run(main())`], { windowsHide: true, stdio: ["pipe", "ignore", "pipe"] });
    peer.log = "";
    peer.stderr.on("data", data => { peer.log += data.toString(); });
    children.push(peer);
    peer.stdin.end(JSON.stringify({ url: config.mcpServers.kane.env.KANE_CONNECTOR_WS_URL, code: pairing.pairing_code }) + "\n");
    await modal.getByText("Agent Connector is online", { exact: true }).waitFor();
    assert.equal((await apiGet("/api/v1/agents")).find(agent => agent.agent_id === pairing.agent_id).status, "ready");
    await modal.getByRole("button", { name: "Close", exact: true }).click();
    await stop(peer);
    await poll(async () => (await apiGet("/api/v1/agents")).find(agent => agent.agent_id === pairing.agent_id).status, status => status === "unavailable");
    await page.getByRole("combobox", { name: "Select an Agent", exact: true }).selectOption(pairing.agent_id);
    await page.locator(".workspace-welcome").waitFor();
    await page.getByRole("combobox", { name: "Select an Agent", exact: true }).selectOption("kanaloa");
    await page.locator(".conversation-header").getByText("Kane architecture review", { exact: true }).waitFor();
  });

  await check("auth failure is explicit", async () => {
    await page.route("**/api/proxy/api/v1/**", route => route.continue({ headers: { ...route.request().headers(), "X-Api-Key": "invalid-ui-test-token" } }));
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText("API access denied", { exact: true }).first().waitFor();
    await page.unroute("**/api/proxy/api/v1/**");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.locator(".conversation-header").getByText("Kane architecture review", { exact: true }).waitFor();
  });

  await check("backend unavailable is explicit", async () => {
    await stop(backend);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByText("Cannot reach Kane", { exact: true }).first().waitFor();
    backend = startApi(); await ready(`${apiBase}/health`, backend);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.locator(".conversation-header").getByText("Kane architecture review", { exact: true }).waitFor();
  });

  const expectedFailureStages = ["auth failure is explicit", "backend unavailable is explicit", "SSE reconnect / no cancel on refresh", "stale approval reports the real backend rejection", "active conversation delete returns 409 / no implicit cancel"];
  assert.deepEqual(pageErrors, [], "Browser runtime errors");
  assert.deepEqual(badResponses.filter(item => !expectedFailureStages.includes(item.stage)), [], "Unexpected HTTP errors");
  assert.deepEqual(consoleErrors.filter(item => !expectedFailureStages.includes(item.stage)), [], "Unexpected console errors");
  console.log(JSON.stringify({ results, output, pageErrors, expectedNegativeResponses: badResponses }, null, 2));
} catch (error) {
  if (page && !page.isClosed()) {
    await page.screenshot({ path: path.join(output, "failure.png"), fullPage: false }).catch(() => {});
    console.error((await page.locator("body").innerText().catch(() => "")).slice(0, 6000));
  }
  console.error(`FAIL ${stage}: ${error.stack}`);
  for (const child of children) console.error(child.log.slice(-5000));
  console.error(`Evidence directory: ${output}`);
  process.exitCode = 1;
} finally {
  await browser?.close();
  for (const child of children.toReversed()) await stop(child).catch(error => { console.error(error.message); process.exitCode = 1; });
  await available(apiPort).catch(() => { console.error(`Test API port ${apiPort} still occupied`); process.exitCode = 1; });
  await available(webPort).catch(() => { console.error(`Test Web port ${webPort} still occupied`); process.exitCode = 1; });
}
