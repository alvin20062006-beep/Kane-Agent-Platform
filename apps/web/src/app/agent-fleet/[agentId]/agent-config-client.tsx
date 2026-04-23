"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { BetaNotice } from "@/components/beta-notice";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { Agent, LocalBridgeAgentState, Task } from "@/lib/octopus-types";

type Initial = {
  data: Agent;
  bridge_state?: LocalBridgeAgentState | null;
  api_profile?: unknown;
};

function boolHint(ok: boolean | null | undefined, okText: string, bad: string) {
  if (ok === true) return <span className="text-emerald-700">{okText}</span>;
  if (ok === false) return <span className="text-red-700">{bad}</span>;
  return <span className="text-zinc-500">—</span>;
}

export function AgentConfigClient({ agentId, initial }: { agentId: string; initial: Initial }) {
  const t = useT();
  const [agent, setAgent] = useState<Agent>(initial.data);
  const [displayName, setDisplayName] = useState(agent.display_name);
  const [adapterId, setAdapterId] = useState(agent.adapter_id ?? "");
  const [mode, setMode] = useState(agent.integration_mode ?? "external");
  const [depth, setDepth] = useState(agent.control_depth ?? "partial");
  const [channelsText, setChannelsText] = useState((agent.integration_channels ?? []).join(", "));
  const [webhookUrl, setWebhookUrl] = useState(agent.control_plane?.webhook_url ?? "");
  const [cliPath, setCliPath] = useState(agent.control_plane?.cli_path ?? "");
  const [shellCommand, setShellCommand] = useState(agent.control_plane?.shell_command ?? "");
  const [workDir, setWorkDir] = useState(agent.control_plane?.working_directory ?? "");
  const [callbackBase, setCallbackBase] = useState(agent.control_plane?.callback_public_base_url ?? "");

  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [testBusy, setTestBusy] = useState(false);
  const [testTaskId, setTestTaskId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Task | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);

  const isBuiltin = agent.type === "builtin" || agent.adapter_id === "builtin_octopus";

  const save = useCallback(async () => {
    setBusy(true);
    setSaveErr(null);
    setSaveMsg(null);
    try {
      const channels = channelsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const control_plane = {
        webhook_url: webhookUrl || null,
        cli_path: cliPath || null,
        shell_command: shellCommand || null,
        working_directory: workDir || null,
        callback_public_base_url: callbackBase || null,
      };
      const res = await apiPatch<{ data: Agent }>(`/agents/${encodeURIComponent(agentId)}`, {
        display_name: displayName,
        adapter_id: isBuiltin ? undefined : adapterId || undefined,
        integration_mode: mode,
        control_depth: depth,
        integration_channels: channels,
        control_plane,
      });
      setAgent(res.data);
      setSaveMsg(t("agent_config.saved"));
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [
    agentId,
    displayName,
    adapterId,
    mode,
    depth,
    channelsText,
    webhookUrl,
    cliPath,
    shellCommand,
    workDir,
    callbackBase,
    isBuiltin,
  ]);

  const registerBridge = async () => {
    setBusy(true);
    setSaveErr(null);
    try {
      await apiPost("/local-bridge/register", {
        agent_id: agentId,
        display_name: displayName,
        adapter_id: adapterId || agent.adapter_id,
        capabilities: agent.capabilities ?? {},
        status: "online",
      });
      setSaveMsg(t("agent_config.bridge_registered"));
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const pollTask = async (taskId: string) => {
    for (let i = 0; i < 45; i++) {
      const r = await apiGet<{ data: Task }>(`/tasks/${encodeURIComponent(taskId)}`);
      const s = r.data.status;
      if (["succeeded", "failed", "cancelled", "expired"].includes(s)) return r.data;
      if (s === "waiting_approval") return r.data;
      await new Promise((res) => setTimeout(res, 1000));
    }
    return null;
  };

  const runTest = async () => {
    setTestBusy(true);
    setTestErr(null);
    setTestResult(null);
    setTestTaskId(null);
    try {
      const res = await apiPost<{
        task_id: string;
        pending_approval?: boolean;
        hints?: string[];
      }>(`/agents/${encodeURIComponent(agentId)}/test-run`, {});
      setTestTaskId(res.task_id);
      const finalTask = await pollTask(res.task_id);
      setTestResult(finalTask);
      if (!finalTask) setTestErr(t("agent_config.test_timeout"));
    } catch (e) {
      setTestErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTestBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {isBuiltin ? (
        <BetaNotice note={t("agent_config.builtin_notice")} />
      ) : (
        <BetaNotice note={t("agent_config.external_notice")} />
      )}

      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3" data-testid="agent-config-labels">
        <div className="text-sm font-semibold">{t("agent_config.labels")}</div>
        <div className="text-sm text-zinc-700 space-y-1">
          <div>
            {t("agent_config.integration_mode")}:{" "}
            <strong className="font-mono">
              {agent.integration_mode ?? (isBuiltin ? "embedded" : "external")}
            </strong>
          </div>
          <div>
            {t("agent_config.channels")}: {(agent.integration_channels ?? []).join(", ") || "—"}
          </div>
          <div>
            {t("agent_config.control_depth")}:{" "}
            <span className="font-mono">{agent.control_depth ?? "—"}</span>
          </div>
          <div>
            {t("agent_config.bridge_state")}:{" "}
            {boolHint(
              Boolean(initial.bridge_state),
              t("agent_config.bridge_registered_short"),
              t("agent_config.bridge_unregistered_short")
            )}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-4" data-testid="agent-config-form">
        <div className="text-sm font-semibold">{t("agent_config.config_section")}</div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-xs text-zinc-600">{t("agent_config.display_name")}</label>
            <input
              data-testid="agent-config-display-name"
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-zinc-600">
              <span className="font-mono">adapter_id</span> {isBuiltin ? `(${t("common.readonly")})` : ""}
            </label>
            <input
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono disabled:bg-zinc-100"
              value={adapterId}
              disabled={isBuiltin}
              onChange={(e) => setAdapterId(e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-xs text-zinc-600">
              <span className="font-mono">integration_mode</span>
            </label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={mode}
              disabled={isBuiltin}
              onChange={(e) => setMode(e.target.value as "embedded" | "external")}
            >
              <option value="embedded">embedded</option>
              <option value="external">external</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-600">
              <span className="font-mono">control_depth</span>
            </label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={depth}
              onChange={(e) => setDepth(e.target.value as NonNullable<Agent["control_depth"]>)}
            >
              <option value="full">full</option>
              <option value="partial">partial</option>
              <option value="assisted">assisted</option>
              <option value="observe_only">observe_only</option>
            </select>
          </div>
        </div>

        <div>
          <label className="text-xs text-zinc-600">
            <span className="font-mono">integration_channels</span>（{t("common.comma_separated")}）
          </label>
          <input
            className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
            value={channelsText}
            onChange={(e) => setChannelsText(e.target.value)}
          />
        </div>

        <div className="border-t border-zinc-100 pt-3 space-y-3">
          <div className="text-xs font-medium text-zinc-600">
            <span className="font-mono">control_plane</span>（{t("agent_config.control_plane_hint")}）
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="text-xs text-zinc-600">
                <span className="font-mono">webhook_url</span>（{t("agent_config.webhook_hint")}）
              </label>
              <input
                className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-600">
                <span className="font-mono">cli_path</span>（{t("agent_config.optional_override")}）
              </label>
              <input
                className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                value={cliPath}
                onChange={(e) => setCliPath(e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <label className="text-xs text-zinc-600">
                <span className="font-mono">shell_command</span>（{t("agent_config.shell_required")}）
              </label>
              <input
                className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                value={shellCommand}
                onChange={(e) => setShellCommand(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-600">
                <span className="font-mono">working_directory</span>
              </label>
              <input
                className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                value={workDir}
                onChange={(e) => setWorkDir(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-600">
                <span className="font-mono">callback_public_base_url</span>（{t("agent_config.callback_hint")}）
              </label>
              <input
                className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                value={callbackBase}
                onChange={(e) => setCallbackBase(e.target.value)}
              />
            </div>
          </div>
          <p className="text-xs text-zinc-500" data-testid="agent-config-env-coming-soon">
            {t("agent_config.env_coming_soon")}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            data-testid="agent-config-save"
            onClick={() => save()}
            className="rounded-md bg-[var(--octo-royal-blue)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {t("action.save")}
          </button>
          {!isBuiltin ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => registerBridge()}
              className="rounded-md border border-zinc-300 px-4 py-2 text-sm text-zinc-800"
            >
              {t("agent_config.register_bridge")}
            </button>
          ) : null}
        </div>
        {saveMsg ? (
          <div className="text-sm text-emerald-800" data-testid="agent-config-save-msg">
            {saveMsg}
          </div>
        ) : null}
        {saveErr ? <div className="text-sm text-red-700">{saveErr}</div> : null}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3" data-testid="agent-config-test-section">
        <div className="text-sm font-semibold">{t("agent_config.test_run")}</div>
        <p className="text-xs text-zinc-600">
          {t("agent_config.test_run_hint")}
        </p>
        <button
          type="button"
          disabled={testBusy}
          data-testid="agent-config-test-run"
          onClick={() => runTest()}
          className="rounded-md bg-[var(--octo-royal-blue)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {testBusy ? t("agent_config.testing") : t("agent_config.send_test")}
        </button>
        {testTaskId ? (
          <div className="text-sm">
            task_id:{" "}
            <Link className="underline font-mono" href={`/tasks/${encodeURIComponent(testTaskId)}`}>
              {testTaskId}
            </Link>
          </div>
        ) : null}
        {testErr ? <div className="text-sm text-red-700">{testErr}</div> : null}
        {testResult ? (
          <div className="rounded-md bg-zinc-50 p-3 text-sm space-y-2" data-testid="agent-config-test-result">
            <div>
              {t("common.status")}: <strong>{testResult.status}</strong>
            </div>
            {testResult.last_error ? (
              <div className="text-red-800">
                {t("common.error")}: {testResult.last_error}
              </div>
            ) : null}
            {testResult.result_summary ? (
              <div>
                <div className="text-xs text-zinc-500">result_summary</div>
                <pre className="mt-1 whitespace-pre-wrap text-xs">{testResult.result_summary}</pre>
              </div>
            ) : null}
            {testResult.status === "waiting_approval" ? (
              <div className="text-xs text-amber-900">{t("agent_config.waiting_approval_hint")}</div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold mb-2">{t("agent_config.api_profile_binding")}</div>
        <p className="text-xs text-zinc-500 mb-2">
          {t("agent_config.api_profile_hint")}
        </p>
        <pre className="text-xs overflow-auto max-h-40 bg-zinc-50 p-2 rounded">
          {JSON.stringify(initial.api_profile ?? null, null, 2)}
        </pre>
      </section>
    </div>
  );
}
