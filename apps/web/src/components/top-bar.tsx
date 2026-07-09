"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useLocale } from "@/lib/i18n/LocaleProvider";
import { apiGet } from "@/lib/api";
import { isExternalAgent } from "@/lib/task-completion";
import type { Agent, ListResponse } from "@/lib/octopus-types";

const PAGE_TITLE_KEYS: Array<[RegExp, string]> = [
  [/^\/conversations/, "nav.conversations"],
  [/^\/cockpit/, "nav.cockpit"],
  [/^\/tasks/, "nav.tasks"],
  [/^\/agent-fleet/, "nav.agents"],
  [/^\/skills/, "nav.skills"],
  [/^\/memory/, "nav.memory"],
  [/^\/files/, "files.title"],
  [/^\/connections/, "connections.title"],
  [/^\/memory-candidates/, "topbar.memory_candidates"],
  [/^\/dashboard/, "nav.dashboard"],
  [/^\/settings/, "nav.settings"],
  [/^\/local-bridge/, "topbar.bridge"],
  [/^\/watchdog/, "topbar.watchdog"],
  [/^\/notifications/, "nav.settings"], // not a main entry; fallback
  [/^\/reports/, "topbar.watchdog"],
  [/^\/help\//, "nav.help"],
];

function resolvePageTitleKey(pathname: string | null): string {
  if (!pathname) return "";
  for (const [re, key] of PAGE_TITLE_KEYS) if (re.test(pathname)) return key;
  return "";
}

// ---------- helpers ----------

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type HealthSummary = {
  status: "ok" | "warn" | "error" | "unknown";
  label: string;
};

async function fetchHealth(): Promise<HealthSummary> {
  try {
    const h = await apiGet<{ status?: string; api?: string }>("/health");
    const s = (h.status ?? h.api ?? "ok").toLowerCase();
    if (s === "ok" || s === "healthy") return { status: "ok", label: "ok" };
    return { status: "warn", label: s };
  } catch {
    return { status: "error", label: "offline" };
  }
}

type BridgeSummary = { online: boolean | null };

async function fetchBridge(): Promise<BridgeSummary> {
  try {
    const b = await apiGet<{ data?: { reachable?: boolean } }>("/local-bridge");
    return { online: !!(b.data?.reachable) };
  } catch {
    return { online: false };
  }
}

type AgentsSummary = { total: number; anomalies: number; external: number };

async function fetchAgents(): Promise<AgentsSummary> {
  try {
    const a = await apiGet<ListResponse<Agent>>("/agents");
    const anomalies = a.items.filter(
      (ag) => ag.status === "offline" || ag.status === "stalled" || ag.status === "degraded"
    ).length;
    const external = a.items.filter((ag) => isExternalAgent(ag)).length;
    return { total: a.items.length, anomalies, external };
  } catch {
    return { total: 0, anomalies: 0, external: 0 };
  }
}

type NotifSummary = { recent: number };

async function fetchNotifSummary(): Promise<NotifSummary> {
  try {
    const d = await apiGet<{ items?: unknown[] }>("/notifications/deliveries?limit=30");
    const items = d.items ?? [];
    return { recent: Math.min(items.length, 99) };
  } catch {
    return { recent: 0 };
  }
}

type TrayMetrics = {
  waitingHandoffs: number;
  openIssues: number;
  activeOrchestrators: number;
};

async function fetchTrayMetrics(): Promise<TrayMetrics> {
  try {
    const m = await apiGet<{
      fault_recovery?: { waiting_handoffs?: number; open_issues?: number };
      orchestrator?: { active_masters?: number };
    }>("/metrics");
    return {
      waitingHandoffs: m.fault_recovery?.waiting_handoffs ?? 0,
      openIssues: m.fault_recovery?.open_issues ?? 0,
      activeOrchestrators: m.orchestrator?.active_masters ?? 0,
    };
  } catch {
    return { waitingHandoffs: 0, openIssues: 0, activeOrchestrators: 0 };
  }
}

type MemoryCandidateSummary = { pending: number };

async function fetchMemoryCandidates(): Promise<MemoryCandidateSummary> {
  try {
    const d = await apiGet<{ items?: { status?: string }[] }>("/memory/candidates?limit=50");
    const items = d.items ?? [];
    const pending = items.filter((m) => m.status === "candidate").length;
    return { pending: Math.min(pending, 99) };
  } catch {
    return { pending: 0 };
  }
}

// ---------- tray icon components ----------

function HealthIcon({
  status,
  label,
  openIssues,
  t,
}: HealthSummary & { openIssues: number; t: (k: string, fb?: string) => string }) {
  const dot =
    status === "ok"
      ? openIssues > 0
        ? "bg-amber-400"
        : "bg-green-500"
      : status === "warn"
      ? "bg-amber-400"
      : status === "error"
      ? "bg-red-500"
      : "bg-zinc-400";
  return (
    <Link
      href="/watchdog"
      title={`${t("topbar.watchdog")}: ${label}${openIssues > 0 ? ` · ${openIssues} ${t("topbar.issues")}` : ""}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <span className={cx("inline-block h-2 w-2 rounded-full", dot)} />
      <span className="hidden sm:inline">{label}</span>
      {openIssues > 0 ? (
        <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-amber-500 px-0.5 text-[9px] font-bold text-white">
          {openIssues > 9 ? "9+" : openIssues}
        </span>
      ) : null}
    </Link>
  );
}

function HandoffIcon({
  count,
  t,
}: {
  count: number;
  t: (k: string, fb?: string) => string;
}) {
  if (count <= 0) return null;
  return (
    <Link
      href="/local-bridge"
      data-testid="topbar-handoffs"
      title={t("topbar.handoffs").replace("{n}", String(count))}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </svg>
      <span className="hidden sm:inline">{t("topbar.handoffs_short")}</span>
      <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-sky-400 px-0.5 text-[9px] font-bold text-sky-950">
        {count > 9 ? "9+" : count}
      </span>
    </Link>
  );
}

function ConnectAgentIcon({
  show,
  t,
}: {
  show: boolean;
  t: (k: string, fb?: string) => string;
}) {
  if (!show) return null;
  return (
    <Link
      href="/local-bridge?connect=1"
      data-testid="topbar-connect-agent"
      title={t("topbar.connect_agent")}
      className="flex items-center gap-1 rounded-md border border-white/20 bg-white/10 px-2 py-1 text-xs font-medium text-[var(--kane-topbar-text)] hover:bg-white/15 transition-colors"
    >
      <span className="text-[10px]">+</span>
      <span className="hidden sm:inline">{t("topbar.connect_agent_short")}</span>
    </Link>
  );
}

function OrchestratorIcon({
  count,
  t,
}: {
  count: number;
  t: (k: string, fb?: string) => string;
}) {
  if (count <= 0) return null;
  return (
    <Link
      href="/orchestrator"
      data-testid="topbar-orchestrator"
      title={t("topbar.orchestrator_active").replace("{n}", String(count))}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      </svg>
      <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-violet-400 px-0.5 text-[9px] font-bold text-violet-950">
        {count > 9 ? "9+" : count}
      </span>
    </Link>
  );
}

function BridgeIcon({ online, t }: BridgeSummary & { t: (k: string, fb?: string) => string }) {
  const state = online === null ? "checking" : online ? "online" : "offline";
  const label =
    online === null
      ? `${t("topbar.bridge")} ...`
      : online
      ? t("topbar.bridge")
      : `${t("topbar.bridge")} offline`;

  return (
    <Link
      href={online === false ? "/local-bridge?connect=1" : "/local-bridge"}
      title={`${t("topbar.bridge")}: ${state}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={online === null ? "text-white/70" : online ? "text-emerald-300" : "text-red-300"}
        aria-hidden
      >
        <path d="M12 22V12" />
        <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
        <path d="M12 2a10 10 0 0 1 10 10" />
        <path d="M12 2a10 10 0 0 0-10 10" />
      </svg>
      {online === false ? (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-red-500" />
      ) : null}
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

function AgentsIcon({ total, anomalies, t }: AgentsSummary & { t: (k: string, fb?: string) => string }) {
  return (
    <Link
      href="/agent-fleet"
      title={`${t("nav.agents")}: ${total} · ${t("topbar.anomalies")} ${anomalies}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <circle cx="12" cy="8" r="4" />
        <path d="M20 21a8 8 0 1 0-16 0" />
      </svg>
      <span className="hidden sm:inline">{total}</span>
      {anomalies > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[9px] text-white font-bold">
          {anomalies}
        </span>
      )}
    </Link>
  );
}

function MemoryCandidateIcon({ pending, t }: MemoryCandidateSummary & { t: (k: string, fb?: string) => string }) {
  if (pending <= 0) return null;
  return (
    <Link
      href="/memory?tab=candidate"
      title={`${t("topbar.memory_candidates")}: ${pending}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
        <rect x="9" y="3" width="6" height="4" rx="1" />
        <path d="M9 12h6M9 16h4" />
      </svg>
      <span
        className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full px-1 text-[9px] font-bold text-black"
        style={{ background: "var(--octo-yellow)" }}
      >
        {pending > 9 ? "9+" : pending}
      </span>
    </Link>
  );
}

function NotifIcon({ recent, t }: NotifSummary & { t: (k: string, fb?: string) => string }) {
  return (
    <Link
      href="/notifications"
      title={`${t("nav.settings")}: ${recent}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      {recent > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-zinc-700 text-[9px] text-white font-bold">
          {recent > 9 ? "9+" : recent}
        </span>
      )}
    </Link>
  );
}

// ---------- main component ----------

function LanguageToggle() {
  const { locale, setLocale, t } = useLocale();
  const next = locale === "zh" ? "en" : "zh";
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      title={t("topbar.switch_language")}
      aria-label={t("topbar.switch_language")}
      className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-[var(--kane-topbar-text)] hover:bg-white/10 transition-colors"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
      <span>{locale === "zh" ? "中" : "EN"}</span>
    </button>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const { t } = useLocale();
  const [health, setHealth] = useState<HealthSummary>({ status: "unknown", label: "…" });
  const [bridge, setBridge] = useState<BridgeSummary>({ online: null });
  const [agentsSummary, setAgentsSummary] = useState<AgentsSummary>({ total: 0, anomalies: 0, external: 0 });
  const [notif, setNotif] = useState<NotifSummary>({ recent: 0 });
  const [memCand, setMemCand] = useState<MemoryCandidateSummary>({ pending: 0 });
  const [trayMetrics, setTrayMetrics] = useState<TrayMetrics>({
    waitingHandoffs: 0,
    openIssues: 0,
    activeOrchestrators: 0,
  });

  const refresh = () => {
    fetchHealth().then(setHealth).catch(() => undefined);
    fetchBridge().then(setBridge).catch(() => undefined);
    fetchAgents().then(setAgentsSummary).catch(() => undefined);
    fetchNotifSummary().then(setNotif).catch(() => undefined);
    fetchMemoryCandidates().then(setMemCand).catch(() => undefined);
    fetchTrayMetrics().then(setTrayMetrics).catch(() => undefined);
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  const pageTitleKey = resolvePageTitleKey(pathname);
  const pageTitle = pageTitleKey ? t(pageTitleKey) : "";
  const needsConnectNudge = agentsSummary.external === 0;

  return (
    <header className="kane-topbar-surface relative flex h-[86px] items-center justify-between overflow-hidden border-b border-[rgba(255,246,231,0.18)] px-10 shadow-[0_10px_24px_rgba(47,22,8,0.18)]">
      <div className="min-w-0 truncate text-[21px] font-semibold text-[var(--kane-topbar-text)] drop-shadow-[0_0_10px_rgba(255,237,206,0.42)]">
        {pageTitle}
      </div>

      <div className="flex items-center gap-0.5">
        <HealthIcon {...health} openIssues={trayMetrics.openIssues} t={t} />
        <BridgeIcon {...bridge} t={t} />
        <HandoffIcon count={trayMetrics.waitingHandoffs} t={t} />
        <OrchestratorIcon count={trayMetrics.activeOrchestrators} t={t} />
        <AgentsIcon {...agentsSummary} t={t} />
        <ConnectAgentIcon show={needsConnectNudge} t={t} />
        <MemoryCandidateIcon {...memCand} t={t} />
        <NotifIcon {...notif} t={t} />
        <LanguageToggle />
      </div>
    </header>
  );
}
