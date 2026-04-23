"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useLocale } from "@/lib/i18n/LocaleProvider";
import { apiGet } from "@/lib/api";
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

type BridgeSummary = { online: boolean };

async function fetchBridge(): Promise<BridgeSummary> {
  try {
    const b = await apiGet<{ data?: { reachable?: boolean } }>("/local-bridge");
    return { online: !!(b.data?.reachable) };
  } catch {
    return { online: false };
  }
}

type AgentsSummary = { total: number; anomalies: number };

async function fetchAgents(): Promise<AgentsSummary> {
  try {
    const a = await apiGet<ListResponse<Agent>>("/agents");
    const anomalies = a.items.filter(
      (ag) => ag.status === "offline" || ag.status === "stalled" || ag.status === "degraded"
    ).length;
    return { total: a.items.length, anomalies };
  } catch {
    return { total: 0, anomalies: 0 };
  }
}

type NotifSummary = { recent: number };

async function fetchNotifSummary(): Promise<NotifSummary> {
  try {
    const d = await apiGet<{ items?: unknown[] }>("/notifications/deliveries");
    const items = d.items ?? [];
    return { recent: Math.min(items.length, 99) };
  } catch {
    return { recent: 0 };
  }
}

type MemoryCandidateSummary = { pending: number };

async function fetchMemoryCandidates(): Promise<MemoryCandidateSummary> {
  try {
    const d = await apiGet<{ items?: { status?: string }[] }>("/memory/candidates");
    const items = d.items ?? [];
    const pending = items.filter((m) => m.status === "candidate").length;
    return { pending: Math.min(pending, 99) };
  } catch {
    return { pending: 0 };
  }
}

// ---------- tray icon components ----------

function HealthIcon({ status, label, t }: HealthSummary & { t: (k: string, fb?: string) => string }) {
  const dot =
    status === "ok"
      ? "bg-green-500"
      : status === "warn"
      ? "bg-amber-400"
      : status === "error"
      ? "bg-red-500"
      : "bg-zinc-400";
  return (
    <Link
      href="/watchdog"
      title={`${t("topbar.watchdog")}: ${label}`}
      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-blue-50 hover:bg-white/15 transition-colors"
    >
      <span className={cx("inline-block h-2 w-2 rounded-full", dot)} />
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

function BridgeIcon({ online, t }: BridgeSummary & { t: (k: string, fb?: string) => string }) {
  return (
    <Link
      href="/local-bridge"
      title={`${t("topbar.bridge")}: ${online ? "online" : "offline"}`}
      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-blue-50 hover:bg-white/15 transition-colors"
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
        className={online ? "text-green-600" : "text-zinc-400"}
        aria-hidden
      >
        <path d="M12 22V12" />
        <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
        <path d="M12 2a10 10 0 0 1 10 10" />
        <path d="M12 2a10 10 0 0 0-10 10" />
      </svg>
      <span className="hidden sm:inline">{online ? t("topbar.bridge") : `${t("topbar.bridge")} ✕`}</span>
    </Link>
  );
}

function AgentsIcon({ total, anomalies, t }: AgentsSummary & { t: (k: string, fb?: string) => string }) {
  return (
    <Link
      href="/agent-fleet"
      title={`${t("nav.agents")}: ${total} · ${t("topbar.anomalies")} ${anomalies}`}
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-blue-50 hover:bg-white/15 transition-colors"
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
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-blue-50 hover:bg-white/15 transition-colors"
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
      className="relative flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-blue-50 hover:bg-white/15 transition-colors"
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
      className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-blue-50 hover:bg-white/15 transition-colors"
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
  const [bridge, setBridge] = useState<BridgeSummary>({ online: false });
  const [agentsSummary, setAgentsSummary] = useState<AgentsSummary>({ total: 0, anomalies: 0 });
  const [notif, setNotif] = useState<NotifSummary>({ recent: 0 });
  const [memCand, setMemCand] = useState<MemoryCandidateSummary>({ pending: 0 });

  const refresh = () => {
    fetchHealth().then(setHealth).catch(() => undefined);
    fetchBridge().then(setBridge).catch(() => undefined);
    fetchAgents().then(setAgentsSummary).catch(() => undefined);
    fetchNotifSummary().then(setNotif).catch(() => undefined);
    fetchMemoryCandidates().then(setMemCand).catch(() => undefined);
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pageTitleKey = resolvePageTitleKey(pathname);
  const pageTitle = pageTitleKey ? t(pageTitleKey) : "";

  return (
    <header className="flex h-12 items-center justify-between border-b border-[var(--octo-blue-deep)] bg-[var(--octo-blue)] px-4">
      <div className="min-w-0 truncate text-sm font-semibold text-white">
        {pageTitle}
      </div>

      <div className="flex items-center gap-0.5">
        <HealthIcon {...health} t={t} />
        <BridgeIcon {...bridge} t={t} />
        <AgentsIcon {...agentsSummary} t={t} />
        <MemoryCandidateIcon {...memCand} t={t} />
        <NotifIcon {...notif} t={t} />
        <LanguageToggle />
      </div>
    </header>
  );
}
