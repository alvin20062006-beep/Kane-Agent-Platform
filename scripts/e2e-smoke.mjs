import { existsSync } from "node:fs";
import os from "node:os";

const apiBase = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:8000";
const bridgeBase = process.env.E2E_BRIDGE_BASE_URL ?? "http://127.0.0.1:8010";
const webBase = process.env.E2E_WEB_BASE_URL ?? "http://localhost:3000";
const navTimeoutMs = Number(process.env.E2E_NAV_TIMEOUT_MS ?? "90000");

const pagePaths = ["/conversations", "/tasks", "/memory", "/dashboard", "/settings", "/local-bridge"];

const errorTextPatterns = [
  /API request failed/i,
  /API\s*\u8bf7\u6c42\u5931\u8d25/i,
  /NEXT_PUBLIC_API_BASE_URL/i,
  /apps\/api/i,
];

const pageChecks = {
  "/dashboard": async (page) => {
    await page.locator('[data-testid="dashboard-metric-tasks"]').waitFor({ timeout: 20000 });
    await page.locator('[data-testid="dashboard-watchdog-hints"]').waitFor({ timeout: 20000 });
  },
  "/settings": async (page) => {
    const bodyText = await page.locator("body").innerText({ timeout: 10000 });
    assert(
      /Platform connectivity|Permission profile|API version|Local Bridge/i.test(bodyText),
      "/settings did not render platform status content or a recognizable fallback"
    );
  },
  "/local-bridge": async (page) => {
    await page.locator('[data-testid="bridge-url-card"]').waitFor({ timeout: 20000 });
    await page.locator('[data-testid="bridge-reachable-card"]').waitFor({ timeout: 20000 });
    await page.locator('[data-testid="bridge-agents-card"]').waitFor({ timeout: 20000 });
  },
};

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function fetchJson(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      // Keep json null; caller can still inspect text.
    }
    return { response, text, json };
  } finally {
    clearTimeout(timeout);
  }
}

async function checkEndpoint(label, url) {
  const started = performance.now();
  let result;
  try {
    result = await fetchJson(url);
  } catch (error) {
    throw new Error(
      `${label} is not reachable at ${url}: ${
        error instanceof Error ? error.message : String(error)
      }. Start API, Web, and Local Bridge before running E2E smoke.`
    );
  }
  const { response, json, text } = result;
  const elapsedMs = Math.round(performance.now() - started);
  assert(response.ok, `${label} failed: ${response.status} ${text.slice(0, 200)}`);
  return { label, url, status: response.status, elapsedMs, statusValue: json?.status ?? null };
}

async function getExistingTaskId() {
  const { response, json, text } = await fetchJson(`${apiBase}/tasks?limit=1`);
  assert(response.ok, `task lookup failed: ${response.status} ${text.slice(0, 200)}`);
  const task = json?.items?.[0];
  return task?.task_id ?? null;
}

async function createSmokeTask() {
  const { response, json, text } = await fetchJson(
    `${apiBase}/tasks`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": "e2e-smoke-create-baseline-task",
      },
      body: JSON.stringify({
        title: "E2E smoke baseline task",
        description: "Created by test:e2e:smoke when the local task list is empty.",
        execution_mode: "commander",
        queue_priority: "low",
      }),
    },
    15000
  );
  assert(response.ok, `smoke task create failed: ${response.status} ${text.slice(0, 200)}`);
  const task = json?.data;
  assert(task?.task_id, `smoke task create returned no task_id: ${text.slice(0, 200)}`);
  return task.task_id;
}

async function ensureSmokeTaskId() {
  return (await getExistingTaskId()) ?? (await createSmokeTask());
}

function candidateBrowsers() {
  const platform = os.platform();
  if (platform === "win32") {
    return [
      "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
      "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    ];
  }
  if (platform === "darwin") {
    return [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ];
  }
  return ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"];
}

async function launchBrowser(chromium) {
  const executablePath = candidateBrowsers().find((path) => existsSync(path));
  if (executablePath) {
    return chromium.launch({ headless: true, executablePath });
  }
  return chromium.launch({ headless: true });
}

async function checkPage(page, path, requiredCheck = pageChecks[path]) {
  const url = `${webBase}${path}`;
  const badResponses = [];
  const failedRequests = [];
  const consoleErrors = [];

  const onResponse = (response) => {
    const responseUrl = response.url();
    const status = response.status();
    if ((responseUrl.startsWith(apiBase) || responseUrl.startsWith(webBase)) && status >= 400) {
      badResponses.push({ url: responseUrl, status });
    }
  };
  const onRequestFailed = (request) => {
    const failure = request.failure()?.errorText ?? "request_failed";
    if (!request.url().includes("hot-update") && !failure.includes("ERR_ABORTED")) {
      failedRequests.push({ url: request.url(), failure });
    }
  };
  const onConsole = (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  };
  const onPageError = (error) => {
    consoleErrors.push(error.message);
  };

  page.on("response", onResponse);
  page.on("requestfailed", onRequestFailed);
  page.on("console", onConsole);
  page.on("pageerror", onPageError);

  try {
    const started = performance.now();
    let response;
    try {
      response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: navTimeoutMs });
    } catch (error) {
      throw new Error(
        `${path} is not reachable at ${url}: ${
          error instanceof Error ? error.message : String(error)
        }. Start API, Web, and Local Bridge before running E2E smoke.`
      );
    }
    const elapsedMs = Math.round(performance.now() - started);
    await page.waitForTimeout(2000);
    assert(response?.ok(), `${path} navigation failed: ${response?.status() ?? "no_response"}`);
    if (requiredCheck) {
      await requiredCheck(page);
    }
    const bodyText = await page.locator("body").innerText({ timeout: 10000 });
    assert(!errorTextPatterns.some((pattern) => pattern.test(bodyText)), `${path} rendered API error text`);
    assert(badResponses.length === 0, `${path} had bad responses: ${JSON.stringify(badResponses)}`);
    assert(failedRequests.length === 0, `${path} had failed requests: ${JSON.stringify(failedRequests)}`);
    assert(consoleErrors.length === 0, `${path} had console errors: ${JSON.stringify(consoleErrors.slice(0, 3))}`);
    return { path, status: response.status(), elapsedMs, ok: true };
  } finally {
    page.off("response", onResponse);
    page.off("requestfailed", onRequestFailed);
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }
}

async function checkTaskDetailPage(page, taskId) {
  const path = `/tasks/${encodeURIComponent(taskId)}`;
  const result = await checkPage(page, path, async (taskPage) => {
    await taskPage.locator('[data-testid="task-summary-card"]').waitFor({ timeout: 20000 });
    await taskPage.locator('[data-testid="task-execution-audit-panel"]').waitFor({ timeout: 20000 });
  });
  return { ...result, taskId };
}

async function checkTasksNavClick(page) {
  await checkPage(page, "/conversations");
  const taskLink = page.locator('a[href="/tasks"]');
  const count = await taskLink.count();
  assert(count === 1, `expected one /tasks navigation link, found ${count}`);

  const started = performance.now();
  await taskLink.click({ timeout: 10000 });
  await page.waitForURL(`${webBase}/tasks`, { timeout: navTimeoutMs });
  await page.waitForLoadState("domcontentloaded", { timeout: navTimeoutMs });
  await page.locator('[data-testid="tasks-table"], [data-testid="create-task-button"]').first().waitFor({
    timeout: 20000,
  });
  const elapsedMs = Math.round(performance.now() - started);
  const bodyText = await page.locator("body").innerText({ timeout: 10000 });
  assert(!errorTextPatterns.some((pattern) => pattern.test(bodyText)), "tasks nav click rendered API error text");
  return { action: "click_conversations_to_tasks", from: "/conversations", to: "/tasks", elapsedMs, ok: true };
}

async function checkTaskRowClick(page, taskId) {
  await checkPage(page, "/tasks");
  const row = page.locator(`[data-testid="task-row-${taskId}"]`);
  const count = await row.count();
  assert(count === 1, `expected one task row for ${taskId}, found ${count}`);

  const started = performance.now();
  await row.click({ timeout: 10000 });
  await page.waitForURL(`${webBase}/tasks/${encodeURIComponent(taskId)}`, { timeout: navTimeoutMs });
  await page.waitForLoadState("domcontentloaded", { timeout: navTimeoutMs });
  await page.locator('[data-testid="task-summary-card"]').waitFor({ timeout: 20000 });
  await page.locator('[data-testid="task-execution-audit-panel"]').waitFor({ timeout: 20000 });
  const elapsedMs = Math.round(performance.now() - started);
  const bodyText = await page.locator("body").innerText({ timeout: 10000 });
  assert(!errorTextPatterns.some((pattern) => pattern.test(bodyText)), "task row click rendered API error text");
  return {
    action: "click_task_row_to_detail",
    from: "/tasks",
    to: `/tasks/${taskId}`,
    elapsedMs,
    ok: true,
  };
}

async function main() {
  const endpointResults = [
    await checkEndpoint("api.health", `${apiBase}/health`),
    await checkEndpoint("bridge.health", `${bridgeBase}/health`),
  ];
  const taskId = await ensureSmokeTaskId();

  const { chromium } = await import("playwright");
  const browser = await launchBrowser(chromium);
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const pageResults = [];
    for (const path of pagePaths) {
      pageResults.push(await checkPage(page, path));
    }
    pageResults.push(await checkTaskDetailPage(page, taskId));
    const interactionResults = [await checkTasksNavClick(page), await checkTaskRowClick(page, taskId)];
    console.log(
      JSON.stringify(
        {
          ok: true,
          apiBase,
          bridgeBase,
          webBase,
          navTimeoutMs,
          endpoints: endpointResults,
          pages: pageResults,
          interactions: interactionResults,
        },
        null,
        2
      )
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(`[e2e-smoke] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
