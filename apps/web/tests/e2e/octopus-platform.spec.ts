import { expect, test, type Page } from "@playwright/test";

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const bridgeBase = process.env.PLAYWRIGHT_BRIDGE_URL ?? "http://127.0.0.1:8010";

function uniqueName(prefix: string) {
  return `${prefix} ${Date.now()} ${Math.random().toString(36).slice(2, 8)}`;
}

async function createTaskViaUi(page: Page, title: string, description: string) {
  await page.goto("/tasks");
  await page.getByTestId("task-title-input").fill(title);
  await page.getByTestId("task-description-input").fill(description);
  await page.getByTestId("create-task-button").click();
  await expect(page.getByTestId("tasks-table")).toContainText(title);
  await page.getByRole("link", { name: title }).click();
  await expect(page).toHaveURL(/\/tasks\/task_/);
}

test.describe("Octopus Platform E2E", () => {
  test("daily conversation flow creates history and memory candidate, then promotes to a task", async ({
    page,
  }) => {
    const conversationTitle = uniqueName("E2E Conversation");
    const rememberText = `remember: ${uniqueName("lightweight memory")}`;

    await page.goto("/conversations");
    await page.getByTestId("conversation-title-input").fill(conversationTitle);
    await page.getByTestId("create-conversation-button").click();

    await expect(page.getByTestId("selected-conversation-meta")).toBeVisible();
    await page.getByTestId("create-memory-candidate-checkbox").check();
    await page.getByTestId("conversation-message-input").fill(rememberText);
    await page.getByTestId("send-message-button").click();

    await expect(page.getByTestId("conversation-history")).toContainText(rememberText);
    await expect(page.getByTestId("conversation-history")).toContainText(
      "Builtin Octopus quick response"
    );
    await expect(page.getByTestId("memory-candidate-notice")).toContainText(
      "Memory candidate created"
    );

    await page.getByTestId("promote-to-task-button").click();
    await expect(page.getByTestId("open-promoted-task-link")).toBeVisible();
    await page.getByTestId("open-promoted-task-link").click();

    await expect(page.getByTestId("task-summary-card")).toBeVisible();
    await expect(page.getByTestId("task-timeline-card")).toContainText(
      "promoted_from_conversation"
    );
    await expect(page.getByTestId("task-timeline-card")).toContainText("agent_assigned");
  });

  test("formal task flow can create, assign, run, and show timeline plus run output", async ({
    page,
  }) => {
    const taskTitle = uniqueName("E2E Formal Task");
    await createTaskViaUi(page, taskTitle, "Run the builtin lifecycle path from the UI.");

    await page.getByTestId("assign-task-button").click();
    // Avoid networkidle: the UI may keep SSE/EventSource connections open.
    await expect(page.getByTestId("task-status-value")).toContainText("assigned");

    await page.getByTestId("run-task-button").click();
    // Avoid networkidle: worker + SSE can keep the network busy.

    // Builtin path should succeed; allow the UI to poll and reload.
    await expect(page.getByTestId("task-status-value")).toContainText("succeeded", { timeout: 60_000 });
    await expect(page.getByTestId("task-live-events")).toContainText("run_started");
    await expect(page.getByTestId("task-live-events")).toContainText("task_succeeded");
    await expect(page.getByTestId("task-runs-card")).toContainText("Execution succeeded");
    await expect(page.getByTestId("task-result-summary")).not.toContainText(
      "No result summary yet."
    );
  });

  test("failed task can be retried and shows failure plus retry events", async ({ page }) => {
    const taskTitle = uniqueName("E2E simulate_fail");
    await createTaskViaUi(
      page,
      taskTitle,
      "simulate_fail to exercise the retry path and failure visibility."
    );

    await page.getByTestId("assign-task-button").click();
    // Avoid networkidle: SSE/EventSource may keep the connection active.
    await page.getByTestId("run-task-button").click();

    await expect(page.getByTestId("task-status-value")).toContainText(/failed|succeeded|waiting_approval/);
    await expect(page.getByTestId("task-status-value")).toContainText("failed", { timeout: 60_000 });
    await expect(page.getByTestId("task-timeline-card")).toContainText("task_failed");

    await page.getByTestId("retry-only-button").click();

    await expect(page.getByTestId("task-status-value")).toContainText("assigned");
    await expect(page.getByTestId("task-timeline-card")).toContainText("retry_requested");

    await page.getByTestId("run-task-button").click();
    await expect(page.getByTestId("task-status-value")).toContainText("failed", { timeout: 60_000 });
  });

  test("bridge, dashboard, watchdog, and external callback flow show real persisted data", async ({
    page,
    request,
  }) => {
    const externalAgentId = `cursor_external_${Date.now()}`;

    const registerApiResponse = await request.post(`${apiBase}/local-bridge/register`, {
      data: {
        agent_id: externalAgentId,
        display_name: "Cursor (bridge E2E)",
        adapter_id: "cursor_cli",
        capabilities: {
          can_code: true,
          supports_structured_task: true,
        },
        workspace_path: "C:\\Users\\Alvin\\章鱼平台",
      },
    });
    expect(registerApiResponse.ok()).toBeTruthy();

    const registerBridgeResponse = await request.post(`${bridgeBase}/agents/register`, {
      data: {
        agent_id: externalAgentId,
        display_name: "Cursor (bridge E2E)",
        adapter_id: "cursor_cli",
        capabilities: {
          can_code: true,
          supports_structured_task: true,
        },
      },
    });
    expect(registerBridgeResponse.ok()).toBeTruthy();

    const heartbeatResponse = await request.post(`${bridgeBase}/agents/heartbeat`, {
      data: {
        agent_id: externalAgentId,
        status: "idle",
      },
    });
    expect(heartbeatResponse.ok()).toBeTruthy();

    await page.goto("/local-bridge");
    await expect(page.getByTestId("bridge-reachable-card")).toContainText("true");
    await expect(page.getByTestId("bridge-agents-card")).toContainText(externalAgentId);

    await page.goto("/agent-adapters");
    await expect(page.getByTestId("agent-adapters-table")).toContainText(externalAgentId);

    const createTaskResponse = await request.post(`${apiBase}/tasks`, {
      data: {
        title: uniqueName("E2E External Task"),
        description: "Create a Cursor bridge handoff and wait for callback.",
        execution_mode: "direct_agent",
      },
    });
    expect(createTaskResponse.ok()).toBeTruthy();
    const createdTask = (await createTaskResponse.json()) as {
      data: { task_id: string };
    };
    const taskId = createdTask.data.task_id;

    const assignResponse = await request.post(`${apiBase}/tasks/${taskId}/assign`, {
      data: { agent_id: externalAgentId },
    });
    expect(assignResponse.ok()).toBeTruthy();

    const runResponse = await request.post(`${apiBase}/tasks/${taskId}/run`);
    expect(runResponse.ok()).toBeTruthy();
    const runPayload = (await runResponse.json()) as {
      run: { run_id: string };
    };
    const runId = runPayload.run.run_id;

    await page.goto(`/tasks/${taskId}`);
    // External handoff may transition queued -> waiting_approval asynchronously.
    await expect(page.getByTestId("task-status-value")).toContainText(
      /queued|waiting_approval|assigned|running|succeeded|failed/
    );
    await expect(page.getByTestId("task-status-value")).toContainText("waiting_approval", { timeout: 60_000 });
    await expect(page.getByTestId("task-live-events")).toContainText("external_handoff");

    const callbackResponse = await request.post(`${apiBase}/local-bridge/result`, {
      timeout: 10_000,
      data: {
        task_id: taskId,
        run_id: runId,
        agent_id: externalAgentId,
        status: "succeeded",
        output: "bridge callback completed successfully from Playwright",
        integration_path: "manual_cursor",
        result_meta: {
          source: "playwright_e2e",
          handoff: true,
        },
      },
    });
    expect(callbackResponse.ok()).toBeTruthy();

    await page.reload();
    await expect(page.getByTestId("task-status-value")).toContainText("succeeded");
    await expect(page.getByTestId("task-result-summary")).toContainText(
      "bridge callback completed successfully from Playwright"
    );

    await page.goto("/dashboard");
    // Match the numeric tile only — "Tasks" + "20" would otherwise falsely trip substring "0".
    await expect(page.getByTestId("dashboard-metric-tasks").locator(".text-2xl")).not.toHaveText("0");
    await expect(page.getByTestId("dashboard-metric-conversations")).toBeVisible();
    await expect(page.getByTestId("dashboard-recovery-posture")).toContainText(
      "Bridge reachable"
    );

    await page.goto("/watchdog");
    await expect(page.getByTestId("watchdog-summary-bridge-reachable")).toContainText("true");
    // Recent events list may show registration, external wait, or handoff depending on timing.
    await expect(page.getByTestId("watchdog-events-card")).toContainText(
      /waiting_external_result|bridge_agent_registered|external_handoff/i
    );
  });

  test("local agent control plane: bridge wizard, add agent, fleet, config PATCH, builtin test run", async ({
    page,
  }) => {
    const aid = `e2e_script_${Date.now()}`;

    await page.goto("/local-bridge");
    await expect(page.getByTestId("bridge-url-card")).toBeVisible();
    await expect(page.getByTestId("bridge-wizard")).toBeVisible();
    await page.getByTestId("bridge-wizard-probe").click();
    await expect(page.getByTestId("bridge-wizard-reachable-label")).toContainText(
      /reachable|unreachable|unknown/,
      { timeout: 20_000 }
    );
    await expect(page.getByTestId("bridge-wizard-connectivity")).toBeVisible();

    await page.goto("/agents/add");
    await expect(page.getByTestId("agents-add-template")).toBeVisible();
    await expect(page.getByTestId("agents-add-template").locator("option")).toHaveCount(4);
    await expect(page.getByTestId("agents-add-honesty")).toContainText(/OPENCLAW|Webhook|OpenClaw/i);
    await page.getByTestId("agents-add-template").selectOption("cursor");
    await expect(page.getByTestId("agents-add-honesty")).toContainText(/Cursor|handoff|闭源/i);
    await page.getByTestId("agents-add-template").selectOption("claude_code");
    await expect(page.getByTestId("agents-add-honesty")).toContainText(/Claude|CLI|闭源/i);
    await page.getByTestId("agents-add-template").selectOption("local_script");
    await expect(page.getByTestId("agents-add-honesty")).toContainText(/shell_command|Bridge.*Shell|Embedded/i);

    await page.getByTestId("agents-add-id").fill(aid);
    await page.getByTestId("agents-add-submit").click();
    await expect(page.getByTestId("agents-add-result")).toContainText("已创建", { timeout: 30_000 });

    await page.goto("/agent-fleet");
    await expect(page.getByText(aid, { exact: true }).first()).toBeVisible({ timeout: 15_000 });

    await page.goto(`/agent-fleet/${encodeURIComponent(aid)}`);
    await expect(page.getByTestId("agent-config-labels")).toContainText("接入方式");
    await expect(page.getByTestId("agent-config-labels")).toContainText("通道");
    await expect(page.getByTestId("agent-config-labels")).toContainText("控制深度");
    await expect(page.getByTestId("agent-config-env-coming-soon")).toBeVisible();

    await page.getByTestId("agent-config-display-name").fill(`E2E Script ${aid}`);
    await page.getByTestId("agent-config-save").click();
    await expect(page.getByTestId("agent-config-save-msg")).toContainText("已保存", { timeout: 15_000 });

    await page.reload();
    await expect(page.getByTestId("agent-config-display-name")).toHaveValue(`E2E Script ${aid}`, {
      timeout: 15_000,
    });

    await page.goto("/agent-fleet/octopus_builtin");
    await expect(page.getByTestId("agent-config-labels")).toBeVisible();
    await page.getByTestId("agent-config-test-run").click();
    await expect(page.getByTestId("agent-config-test-result")).toContainText(/succeeded|failed|waiting_approval/, {
      timeout: 90_000,
    });
  });
});
