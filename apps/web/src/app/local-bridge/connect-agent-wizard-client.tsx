"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { apiPost } from "@/lib/api";
import { COMPLETION_MODE_TITLE_KEYS } from "@/lib/completion-mode-labels";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { CompletionMode } from "@/lib/task-completion";

type ConnectMode = "http_webhook" | "cli_sync" | "handoff_only" | "local_script";

type SkillResult<T> = {
  ok: boolean;
  output?: T;
  error?: string | null;
};

type GuideOutput = {
  steps: Array<{ id: string; title: string; detail: string }>;
  recommended_mode: ConnectMode;
};

type ProbeOutput = {
  ready: boolean;
  bridge: { reachable?: boolean | null; url?: string };
  hints?: string[];
};

type DraftOutput = {
  agent_create_body: Record<string, unknown>;
  completion_mode: CompletionMode;
};

type RegisterOutput = {
  agent_id: string;
  display_name: string;
  completion_mode: CompletionMode;
  fleet_url: string;
};

type TestRunOutput = {
  task_id: string;
  run_id?: string | null;
  task_status?: string | null;
};

async function runSkill<T>(
  step: string,
  taskId: string | null,
  extra: Record<string, unknown> = {},
): Promise<SkillResult<T>> {
  const res = await apiPost<{ data: { ok: boolean; output?: T; error?: string | null } }>(
    "/skills/skill_connect_agent/execute",
    { input: { step, ...extra }, task_id: taskId },
  );
  return { ok: res.data.ok, output: res.data.output, error: res.data.error };
}

const MODES: ConnectMode[] = ["http_webhook", "cli_sync", "handoff_only", "local_script"];

export function ConnectAgentWizard({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const t = useT();
  const [open, setOpen] = useState(defaultOpen);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [guide, setGuide] = useState<GuideOutput | null>(null);
  const [probeOk, setProbeOk] = useState<boolean | null>(null);
  const [mode, setMode] = useState<ConnectMode>("http_webhook");
  const [displayName, setDisplayName] = useState("My HTTP Agent");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [cliPath, setCliPath] = useState("");
  const [shellCommand, setShellCommand] = useState("echo kane-bridge-ok");
  const [draft, setDraft] = useState<DraftOutput | null>(null);
  const [registered, setRegistered] = useState<RegisterOutput | null>(null);
  const [testResult, setTestResult] = useState<TestRunOutput | null>(null);
  const [phase, setPhase] = useState<"intro" | "configure" | "confirm" | "done">("intro");
  const [auditTaskId, setAuditTaskId] = useState<string | null>(null);

  const ensureAuditTask = useCallback(async (): Promise<string> => {
    if (auditTaskId) return auditTaskId;
    const created = await apiPost<{ data: { task_id: string } }>("/tasks", {
      title: "Connect external agent (wizard)",
      description: "Audit trail for skill_connect_agent wizard steps.",
      execution_mode: "direct_agent",
    });
    const id = created.data.task_id;
    setAuditTaskId(id);
    return id;
  }, [auditTaskId]);

  const refreshProbe = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const taskId = await ensureAuditTask();
      const [g, p] = await Promise.all([
        runSkill<GuideOutput>("guide", taskId),
        runSkill<ProbeOutput>("probe", taskId),
      ]);
      if (g.output) {
        setGuide(g.output);
        setMode(g.output.recommended_mode);
      }
      setProbeOk(Boolean(p.output?.ready));
      if (!p.ok) setErr(p.error ?? "bridge_unreachable");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [ensureAuditTask]);

  useEffect(() => {
    if (open && probeOk === null) void refreshProbe();
  }, [open, probeOk, refreshProbe]);

  const buildPayload = () => ({
    mode,
    display_name: displayName,
    webhook_url: webhookUrl,
    cli_path: cliPath,
    shell_command: shellCommand,
  });

  const runDraft = async () => {
    setBusy(true);
    setErr(null);
    try {
      const taskId = await ensureAuditTask();
      const res = await runSkill<DraftOutput>("draft", taskId, buildPayload());
      if (!res.ok || !res.output) throw new Error(res.error ?? "draft_failed");
      setDraft(res.output);
      setPhase("confirm");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runRegister = async () => {
    setBusy(true);
    setErr(null);
    try {
      const taskId = await ensureAuditTask();
      const res = await runSkill<RegisterOutput>("register", taskId, {
        ...buildPayload(),
        confirmed: true,
        register_bridge: true,
      });
      if (!res.ok || !res.output) throw new Error(res.error ?? "register_failed");
      setRegistered(res.output);
      const test = await runSkill<TestRunOutput>("test_run", taskId, { agent_id: res.output.agent_id });
      if (test.output) setTestResult(test.output);
      setPhase("done");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        data-testid="connect-agent-open"
        className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
        onClick={() => setOpen(true)}
      >
        {t("connect_agent.open")}
      </button>
    );
  }

  return (
    <section
      data-testid="connect-agent-wizard"
      className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-4 space-y-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-emerald-950">{t("connect_agent.title")}</div>
          <p className="mt-1 text-xs text-emerald-900/80">{t("connect_agent.subtitle")}</p>
        </div>
        <button type="button" className="text-xs text-zinc-600 underline" onClick={() => setOpen(false)}>
          {t("connect_agent.collapse")}
        </button>
      </div>

      {guide ? (
        <ol className="list-decimal space-y-1 pl-5 text-xs text-emerald-950/90">
          {guide.steps.map((s) => (
            <li key={s.id}>
              <span className="font-medium">{s.title}</span> — {s.detail}
            </li>
          ))}
        </ol>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full border border-emerald-300 bg-white px-2 py-0.5">
          Bridge: {probeOk === null ? "…" : probeOk ? t("common.yes") : t("common.no")}
        </span>
        <button
          type="button"
          disabled={busy}
          className="underline text-emerald-800"
          onClick={() => void refreshProbe()}
        >
          {t("connect_agent.retry_probe")}
        </button>
      </div>

      {phase === "intro" ? (
        <div className="space-y-3">
          <p className="text-xs text-zinc-700">{t("connect_agent.intro")}</p>
          <button
            type="button"
            disabled={busy || probeOk === false}
            data-testid="connect-agent-start"
            className="rounded-md bg-zinc-900 px-3 py-2 text-xs text-white disabled:opacity-50"
            onClick={() => setPhase("configure")}
          >
            {t("connect_agent.start")}
          </button>
        </div>
      ) : null}

      {phase === "configure" ? (
        <div className="space-y-3 text-sm">
          <div>
            <label className="text-xs text-zinc-600">{t("connect_agent.mode")}</label>
            <select
              data-testid="connect-agent-mode"
              className="mt-1 w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as ConnectMode)}
            >
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {t(`connect_agent.mode_${m}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-600">{t("connect_agent.display_name")}</label>
            <input
              data-testid="connect-agent-display-name"
              className="mt-1 w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          {mode === "http_webhook" ? (
            <div>
              <label className="text-xs text-zinc-600">{t("connect_agent.webhook_url")}</label>
              <input
                data-testid="connect-agent-webhook"
                className="mt-1 w-full rounded border border-zinc-200 px-2 py-1.5 text-sm font-mono text-xs"
                placeholder="https://example.com/agent-hook (optional → handoff)"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
              />
            </div>
          ) : null}
          {mode === "cli_sync" ? (
            <div>
              <label className="text-xs text-zinc-600">{t("connect_agent.cli_path")}</label>
              <input
                className="mt-1 w-full rounded border border-zinc-200 px-2 py-1.5 text-sm font-mono text-xs"
                placeholder="claude / codex / your-cli"
                value={cliPath}
                onChange={(e) => setCliPath(e.target.value)}
              />
            </div>
          ) : null}
          {mode === "local_script" ? (
            <div>
              <label className="text-xs text-zinc-600">{t("connect_agent.shell_command")}</label>
              <input
                className="mt-1 w-full rounded border border-zinc-200 px-2 py-1.5 text-sm font-mono text-xs"
                value={shellCommand}
                onChange={(e) => setShellCommand(e.target.value)}
              />
            </div>
          ) : null}
          <button
            type="button"
            disabled={busy}
            data-testid="connect-agent-draft"
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-xs"
            onClick={() => void runDraft()}
          >
            {t("connect_agent.preview")}
          </button>
        </div>
      ) : null}

      {phase === "confirm" && draft ? (
        <div className="space-y-3 text-xs">
          <div className="rounded border border-zinc-200 bg-white p-3 font-mono whitespace-pre-wrap">
            {JSON.stringify(draft.agent_create_body, null, 2)}
          </div>
          <p className="text-zinc-700">
            {t("connect_agent.completion_mode")}: {t(COMPLETION_MODE_TITLE_KEYS[draft.completion_mode])}
          </p>
          <button
            type="button"
            disabled={busy}
            data-testid="connect-agent-register"
            className="rounded-md bg-emerald-700 px-3 py-2 text-xs text-white disabled:opacity-50"
            onClick={() => void runRegister()}
          >
            {t("connect_agent.confirm_register")}
          </button>
        </div>
      ) : null}

      {phase === "done" && registered ? (
        <div className="space-y-2 text-sm text-emerald-950">
          <div data-testid="connect-agent-success">
            {t("connect_agent.success").replace("{name}", registered.display_name)}
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Link href={registered.fleet_url} className="underline">
              {t("connect_agent.open_fleet")}
            </Link>
            <Link href="/local-bridge" className="underline">
              {t("task_detail.open_bridge")}
            </Link>
            {testResult?.task_id ? (
              <Link href={`/tasks/${encodeURIComponent(testResult.task_id)}`} className="underline">
                {t("connect_agent.open_test_task")}
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}

      {err ? (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">{err}</div>
      ) : null}
    </section>
  );
}
