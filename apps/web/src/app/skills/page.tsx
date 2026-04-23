"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { apiGet, apiPost, getApiBaseUrl } from "@/lib/api";
import type { ListResponse } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";

type Skill = {
  skill_id: string;
  name: string;
  version: string;
  category: string;
  description?: string | null;
  risk_level: "low" | "medium" | "high";
  default_execution_policy: "auto" | "notify" | "confirm";
  skill_scope?: "platform" | "agent_private";
  owner_agent_id?: string | null;
  enabled?: boolean;
};

// ---------- Helpers ----------

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

async function apiPatch(path: string, body: unknown) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} ${res.status}`);
  return res.json();
}

async function apiDelete(path: string) {
  const res = await fetch(`${getApiBaseUrl()}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} ${res.status}`);
  return res.json();
}

// ---------- RowMenu ----------

type MenuItem =
  | {
      label: string;
      onClick: () => void;
      danger?: boolean;
      disabled?: boolean;
      hint?: string;
    }
  | { separator: true };

function RowMenu({ items }: { items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label="more"
        className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="5" cy="12" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="19" cy="12" r="2" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-1 min-w-[200px] rounded-md border border-zinc-200 bg-white py-1 shadow-lg"
        >
          {items.map((item, idx) => {
            if ("separator" in item)
              return <div key={idx} className="my-1 border-t border-zinc-100" />;
            return (
              <button
                key={idx}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                title={item.hint}
                onClick={(e) => {
                  e.stopPropagation();
                  setOpen(false);
                  item.onClick();
                }}
                className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  item.danger ? "text-red-600 hover:bg-red-50" : "text-zinc-700 hover:bg-zinc-50"
                }`}
              >
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------- Card ----------

function SkillIcon({ skill }: { skill: Skill }) {
  const isPrivate = skill.skill_scope === "agent_private";
  return (
    <div
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
      style={{
        background: isPrivate ? "var(--octo-yellow-soft)" : "var(--octo-blue-soft)",
        color: isPrivate ? "var(--octo-yellow)" : "var(--octo-blue)",
      }}
      aria-hidden
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill="currentColor" stroke="none" />
      </svg>
    </div>
  );
}

function SkillCard({
  skill,
  onClick,
  menuItems,
}: {
  skill: Skill;
  onClick: () => void;
  menuItems: MenuItem[];
}) {
  const t = useT();
  const disabled = skill.enabled === false;
  return (
    <div
      className={cx(
        "group relative w-full rounded-xl border bg-white p-4 transition-all hover:shadow-sm",
        disabled ? "border-zinc-200 opacity-60" : "border-zinc-200 hover:border-zinc-300"
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className="block w-full text-left"
        aria-label={skill.name}
      >
        <div className="flex items-start gap-3">
          <SkillIcon skill={skill} />
          <div className="min-w-0 flex-1 pr-8">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold text-zinc-900">{skill.name}</span>
              {skill.skill_scope === "agent_private" ? (
                <span className="shrink-0 rounded-full bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600">
                  {t("skills.badge_private")}
                </span>
              ) : (
                <span className="shrink-0 rounded-full bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600">
                  {t("skills.badge_platform")}
                </span>
              )}
              {disabled && (
                <span className="shrink-0 rounded-full bg-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-600">
                  {t("skills.badge_disabled")}
                </span>
              )}
            </div>
            {skill.description && (
              <div className="mt-1.5 line-clamp-2 text-xs text-zinc-500">{skill.description}</div>
            )}
          </div>
        </div>
      </button>

      {/* Hover / always-visible ⋯ menu at top-right */}
      <div className="absolute right-2 top-2">
        <RowMenu items={menuItems} />
      </div>
    </div>
  );
}

// ---------- Detail Drawer (read-only preview) ----------

function SkillDetail({
  skill,
  onClose,
  onUse,
  busy,
  useOutput,
}: {
  skill: Skill;
  onClose: () => void;
  onUse: () => void;
  busy: boolean;
  useOutput: string | null;
}) {
  const t = useT();
  const disabled = skill.enabled === false;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30 transition-opacity" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("skills.detail_title")}
        className="fixed right-0 top-0 z-50 h-full w-full max-w-md overflow-y-auto border-l border-zinc-200 bg-white shadow-xl"
      >
        <div className="sticky top-0 flex items-center justify-between border-b border-zinc-200 bg-white px-5 py-4">
          <div className="text-sm font-semibold text-zinc-800">{t("skills.detail_title")}</div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
            aria-label={t("common.close")}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-5 p-5">
          <div className="flex items-start gap-3">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl"
              style={{
                background: skill.skill_scope === "agent_private" ? "var(--octo-yellow-soft)" : "var(--octo-blue-soft)",
                color: skill.skill_scope === "agent_private" ? "var(--octo-yellow)" : "var(--octo-blue)",
              }}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold text-zinc-900">{skill.name}</h2>
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600">
                  {skill.skill_scope === "agent_private"
                    ? t("skills.badge_private")
                    : t("skills.badge_platform")}
                </span>
                {disabled && (
                  <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-[11px] text-zinc-600">
                    {t("skills.badge_disabled")}
                  </span>
                )}
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-zinc-400">
                {skill.skill_id} · v{skill.version}
              </div>
            </div>
          </div>

          {skill.description && (
            <div className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-700">
              {skill.description}
            </div>
          )}

          <div className="grid gap-2 rounded-lg border border-zinc-200 bg-zinc-50/50 p-3 text-xs">
            <div className="flex justify-between">
              <span className="text-zinc-500">{t("skills.category")}</span>
              <span className="text-zinc-700">{skill.category}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">{t("skills.risk")}</span>
              <span className="text-zinc-700">{skill.risk_level}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">{t("skills.policy")}</span>
              <span className="text-zinc-700">{skill.default_execution_policy}</span>
            </div>
            {skill.owner_agent_id && (
              <div className="flex justify-between">
                <span className="text-zinc-500">{t("skills.owner_agent")}</span>
                <span className="font-mono text-zinc-700">{skill.owner_agent_id}</span>
              </div>
            )}
          </div>

          {useOutput && (
            <div>
              <div className="mb-1 text-[11px] font-medium text-zinc-500">output</div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-[11px] text-zinc-100">
                {useOutput}
              </pre>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 border-t border-zinc-200 bg-white px-5 py-3">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="text-[10px] text-zinc-400">
              {/* Read-only hint — all mutating actions live in the ⋯ menu */}
              {t("skills.detail_title")}
            </span>
            <button
              type="button"
              disabled={busy || disabled}
              onClick={onUse}
              className="rounded-full px-5 py-2 text-xs font-semibold text-white disabled:opacity-50"
              style={{ background: disabled ? "#a1a1aa" : "#111" }}
            >
              {busy ? t("action.loading") : t("skills.use")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------- Placeholder modals (upload/new – backend不支持，明确标 Beta) ----------

function BetaPlaceholderModal({ title, onClose }: { title: string; onClose: () => void }) {
  const t = useT();
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-zinc-200 bg-white shadow-xl"
      >
        <div className="space-y-3 p-5">
          <div className="flex items-center gap-2">
            <span
              className="inline-flex h-8 w-8 items-center justify-center rounded-full"
              style={{ background: "var(--octo-yellow-soft)", color: "var(--octo-yellow)" }}
              aria-hidden
            >
              ⚡
            </span>
            <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
          </div>
          <p className="text-xs leading-relaxed text-zinc-600">
            {t("skills.upload_beta_body_1")}
            {t("skills.upload_beta_body_2")}
            <code className="rounded bg-zinc-100 px-1 font-mono">skills_repo</code>
            {t("skills.upload_beta_body_3")}
            <code className="rounded bg-zinc-100 px-1 font-mono">PATCH /skills/{"{id}"}</code>
            {t("skills.upload_beta_body_4")}
          </p>
          <div className="pt-2 text-right">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-zinc-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
            >
              OK
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------- Page ----------

export default function SkillsPage() {
  const t = useT();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Skill | null>(null);
  const [query, setQuery] = useState("");
  const [showDisabled, setShowDisabled] = useState(false);
  const [placeholder, setPlaceholder] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [useOutput, setUseOutput] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<ListResponse<Skill>>("/skills");
      setSkills(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const flash = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const toggleEnabled = async (skill: Skill) => {
    const nextEnabled = skill.enabled === false;
    setBusy(true);
    try {
      await apiPatch(`/skills/${encodeURIComponent(skill.skill_id)}`, { enabled: nextEnabled });
      await load();
      flash(nextEnabled ? t("action.enable") : t("action.disable"));
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const uninstall = async (skill: Skill) => {
    if (!confirm(`${t("action.uninstall")} ${skill.name}?`)) return;
    setBusy(true);
    try {
      await apiDelete(`/skills/${encodeURIComponent(skill.skill_id)}`);
      await load();
      if (selected?.skill_id === skill.skill_id) setSelected(null);
      flash(t("action.uninstall"));
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const publishToCenter = async (skill: Skill) => {
    setBusy(true);
    try {
      await apiPost(`/skills/${encodeURIComponent(skill.skill_id)}/publish`, {});
      await load();
      flash(t("action.publish_to_center"));
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const useSkill = async (skill: Skill) => {
    setBusy(true);
    setUseOutput(null);
    try {
      const res = await apiPost<{ data: { ok: boolean; output?: unknown; error?: string } }>(
        `/skills/${encodeURIComponent(skill.skill_id)}/execute`,
        { input: {} }
      );
      setUseOutput(JSON.stringify(res.data, null, 2));
    } catch (e) {
      setUseOutput(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const buildMenuItems = (skill: Skill): MenuItem[] => {
    const disabled = skill.enabled === false;
    return [
      {
        label: disabled ? t("action.enable") : t("action.disable"),
        onClick: () => toggleEnabled(skill),
        disabled: busy,
      },
      ...(skill.skill_scope === "agent_private"
        ? [
            {
              label: t("action.publish_to_center"),
              onClick: () => publishToCenter(skill),
              disabled: busy,
            } as MenuItem,
          ]
        : []),
      { separator: true } as MenuItem,
      {
        label: t("action.uninstall"),
        onClick: () => uninstall(skill),
        danger: true,
        disabled: busy,
      },
    ];
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((s) => {
      if (s.enabled === false && !showDisabled) return false;
      if (!q) return true;
      return (
        s.name.toLowerCase().includes(q) ||
        s.skill_id.toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q)
      );
    });
  }, [skills, query, showDisabled]);

  const disabledCount = skills.filter((s) => s.enabled === false).length;

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
            {t("skills.title")}
          </h1>
          <p className="mt-1 text-sm text-zinc-600">{t("skills.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPlaceholder(t("skills.upload"))}
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-4 py-2 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
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
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            {t("skills.upload")}
          </button>
          <button
            type="button"
            onClick={() => setPlaceholder(t("skills.new"))}
            className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
            style={{ background: "var(--octo-royal-blue)" }}
          >
            + {t("skills.new")}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] max-w-md flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("skills.search_placeholder")}
            className="w-full rounded-full border border-zinc-200 bg-white px-4 py-2 pl-9 text-sm outline-none focus:border-zinc-400"
          />
          <svg
            className="absolute left-3 top-2.5 text-zinc-400"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        {disabledCount > 0 && (
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-600">
            <input
              type="checkbox"
              checked={showDisabled}
              onChange={(e) => setShowDisabled(e.target.checked)}
              className="rounded border-zinc-300"
            />
            {t("skills.show_disabled")} ({disabledCount})
          </label>
        )}
        {toast && (
          <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11px] text-zinc-600">{toast}</span>
        )}
      </div>

      {loading && <div className="py-12 text-center text-sm text-zinc-400">{t("action.loading")}</div>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-200 py-16 text-center">
          <div className="text-sm text-zinc-500">{query ? t("skills.no_match") : t("skills.empty")}</div>
        </div>
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((skill) => (
            <SkillCard
              key={skill.skill_id}
              skill={skill}
              menuItems={buildMenuItems(skill)}
              onClick={() => {
                setUseOutput(null);
                setSelected(skill);
              }}
            />
          ))}
        </div>
      )}

      {selected && (
        <SkillDetail
          skill={selected}
          busy={busy}
          useOutput={useOutput}
          onClose={() => setSelected(null)}
          onUse={() => useSkill(selected)}
        />
      )}
      {placeholder && <BetaPlaceholderModal title={placeholder} onClose={() => setPlaceholder(null)} />}
    </div>
  );
}
