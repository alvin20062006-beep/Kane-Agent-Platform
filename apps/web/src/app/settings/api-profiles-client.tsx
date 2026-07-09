"use client";

import { useEffect, useMemo, useState } from "react";

import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { Agent, ApiProfile, ListResponse } from "@/lib/octopus-types";

type AgentDetail = {
  data: Agent;
  api_profile?: {
    binding: { profile_id: string } | null;
    profile: ApiProfile | null;
  };
};

type OctopusBindingStatus = {
  binding: { profile_id: string } | null;
  profile: ApiProfile | null;
};

const inputClass =
  "w-full rounded-md border border-[var(--kane-border)] bg-white/55 px-3 py-2.5 text-sm text-[var(--foreground)] shadow-[0_1px_0_rgba(255,255,255,0.6)_inset]";

const secondaryButton =
  "rounded-md border border-[var(--kane-border)] bg-white/55 px-3.5 py-2 text-sm text-[var(--kane-walnut)] shadow-[0_1px_0_rgba(255,255,255,0.6)_inset] transition hover:border-[var(--kane-amber)] hover:bg-white/75 disabled:opacity-50";

const primaryButton =
  "rounded-md bg-[linear-gradient(180deg,var(--kane-walnut),var(--kane-walnut-deep))] px-4 py-2 text-sm text-white shadow-[0_8px_18px_rgba(81,39,7,0.18)] transition hover:bg-[var(--kane-walnut-deep)] disabled:opacity-50";

export function ApiProfilesClient() {
  const t = useT();
  const [profiles, setProfiles] = useState<ApiProfile[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("octopus_builtin");
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [octopusBinding, setOctopusBinding] = useState<OctopusBindingStatus | null>(null);
  const [activateProfileId, setActivateProfileId] = useState<string>("");
  const [editingProfileId, setEditingProfileId] = useState<string>("");
  const [form, setForm] = useState({
    name: "",
    provider: "openai_compatible" as ApiProfile["provider"],
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    api_key: "",
    is_default: false,
  });
  const [log, setLog] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const [p, a] = await Promise.all([
      apiGet<ListResponse<ApiProfile>>("/api-profiles"),
      apiGet<ListResponse<Agent>>("/agents"),
    ]);
    setProfiles(p.items);
    setAgents(a.items);
    if (a.items.length && !selectedAgentId) setSelectedAgentId(a.items[0].agent_id);
    try {
      const detail = await apiGet<{ api_profile: OctopusBindingStatus }>("/agents/octopus_builtin");
      setOctopusBinding(detail.api_profile ?? null);
      if (detail.api_profile?.binding?.profile_id) {
        setActivateProfileId(detail.api_profile.binding.profile_id);
      }
    } catch {
      // The built-in agent may not exist in older local data.
    }
  };

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const agentBindingLabel = useMemo(() => {
    const p = profiles.find((x) => x.profile_id === selectedProfileId);
    return p ? `${p.name} (${p.provider})` : "";
  }, [profiles, selectedProfileId]);

  const onCreate = async () => {
    setBusy(true);
    setLog("");
    try {
      const res = await apiPost("/api-profiles", {
        profile_id: editingProfileId || null,
        ...form,
        api_key: form.api_key || null,
      });
      setLog(JSON.stringify(res, null, 2));
      setForm((f) => ({ ...f, api_key: "" }));
      setEditingProfileId("");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (p: ApiProfile) => {
    setEditingProfileId(p.profile_id);
    setForm({
      name: p.name ?? "",
      provider: p.provider,
      base_url: p.base_url ?? "",
      model: p.model ?? "",
      api_key: "",
      is_default: Boolean(p.is_default),
    });
    setLog(JSON.stringify({ editing: p.profile_id }, null, 2));
  };

  const clearEdit = () => {
    setEditingProfileId("");
    setForm({
      name: "",
      provider: "openai_compatible",
      base_url: "https://api.openai.com/v1",
      model: "gpt-4.1-mini",
      api_key: "",
      is_default: false,
    });
  };

  const onDelete = async (profile_id: string) => {
    setBusy(true);
    setLog("");
    try {
      const res = await apiDelete(`/api-profiles/${encodeURIComponent(profile_id)}`);
      setLog(JSON.stringify(res, null, 2));
      if (editingProfileId === profile_id) clearEdit();
      if (selectedProfileId === profile_id) setSelectedProfileId("");
      if (activateProfileId === profile_id) setActivateProfileId("");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const onBind = async () => {
    if (!selectedAgentId || !selectedProfileId) return;
    setBusy(true);
    setLog("");
    try {
      const res = await apiPost(`/agents/${encodeURIComponent(selectedAgentId)}/api-profile`, {
        profile_id: selectedProfileId,
      });
      setLog(JSON.stringify(res, null, 2));
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const onInspectAgent = async () => {
    if (!selectedAgentId) return;
    setBusy(true);
    setLog("");
    try {
      const res = await apiGet<AgentDetail>(`/agents/${encodeURIComponent(selectedAgentId)}`);
      setLog(JSON.stringify(res, null, 2));
    } finally {
      setBusy(false);
    }
  };

  const onActivateOctopus = async () => {
    if (!activateProfileId) return;
    setBusy(true);
    setLog("");
    try {
      const res = await apiPost("/agents/octopus_builtin/api-profile", {
        profile_id: activateProfileId,
      });
      setLog(JSON.stringify(res, null, 2));
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const onTestProfile = async (profile_id: string) => {
    setBusy(true);
    setLog("");
    try {
      const res = await apiPost<{ data: { ok?: boolean; error?: string; status_code?: number } }>(
        `/api-profiles/${encodeURIComponent(profile_id)}/test`,
        {},
      );
      setLog(JSON.stringify(res, null, 2));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-5">
      <div className="kane-card kane-grain space-y-3 border-2 border-[var(--kane-walnut)] p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-[var(--kane-walnut)]">
            {t("profiles.section.activation")}
          </span>
          {octopusBinding?.profile ? (
            <span className="rounded-full border border-emerald-200 bg-[var(--kane-moss-soft)] px-2 py-0.5 text-xs font-medium text-[var(--kane-moss)]">
              {t("profiles.activation.active")
                .replace("{name}", octopusBinding.profile.name)
                .replace("{model}", octopusBinding.profile.model)}
            </span>
          ) : (
            <span className="rounded-full border border-amber-200 bg-[var(--kane-amber-soft)] px-2 py-0.5 text-xs font-medium text-[var(--kane-amber-deep)]">
              {t("profiles.activation.inactive")}
            </span>
          )}
        </div>
        <p className="text-xs text-[var(--kane-muted)]">{t("profiles.activation.hint")}</p>
        {profiles.length === 0 ? (
          <p className="text-xs text-[var(--kane-muted)]">{t("profiles.activation.empty")}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <select
              className={inputClass}
              value={activateProfileId}
              onChange={(e) => setActivateProfileId(e.target.value)}
            >
              <option value="">{t("profiles.activation.select_placeholder")}</option>
              {profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.name} - {p.provider} - {p.model}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy || !activateProfileId}
              onClick={onActivateOctopus}
              className={primaryButton}
            >
              {t("profiles.activation.activate")}
            </button>
          </div>
        )}
      </div>

      <div>
        <div className="text-sm font-semibold text-[var(--kane-walnut)]">{t("profiles.section.main")}</div>
        <div className="mt-1 text-xs text-[var(--kane-muted)]">{t("profiles.intro")}</div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="kane-card kane-grain space-y-3 p-5">
          <div className="text-sm font-semibold text-[var(--kane-walnut)]">{t("profiles.section.new")}</div>
          {editingProfileId ? (
            <div className="rounded-md border border-amber-200 bg-[var(--kane-amber-soft)] px-3 py-2 text-xs text-[var(--kane-amber-deep)]">
              {t("profiles.form.editing") || "Editing"}{" "}
              <span className="font-mono">{editingProfileId}</span>
              <button
                type="button"
                disabled={busy}
                onClick={clearEdit}
                className="ml-2 rounded-md border border-amber-200 bg-white/60 px-2 py-1 text-xs disabled:opacity-50"
              >
                {t("profiles.form.cancel") || "Cancel"}
              </button>
            </div>
          ) : null}
          <input
            className={inputClass}
            placeholder={t("profiles.form.name_ph")}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <div className="grid gap-2 md:grid-cols-2">
            <select
              className={inputClass}
              value={form.provider}
              onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value as ApiProfile["provider"] }))}
            >
              <option value="openai_compatible">openai_compatible</option>
              <option value="anthropic_compatible">anthropic_compatible</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-[var(--kane-muted)]">
              <input
                className="kane-checkbox h-4 w-4"
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              {t("profiles.form.default_label")}
            </label>
          </div>
          <input
            className={`${inputClass} font-mono`}
            placeholder={t("profiles.form.base_ph")}
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
          />
          <input
            className={`${inputClass} font-mono`}
            placeholder={t("profiles.form.model_ph")}
            value={form.model}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
          />
          <input
            type="password"
            className={`${inputClass} font-mono`}
            placeholder={t("profiles.form.key_ph")}
            value={form.api_key}
            onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
          />
          <button
            type="button"
            disabled={busy || !form.name.trim()}
            onClick={onCreate}
            className={primaryButton}
          >
            {editingProfileId ? (t("profiles.form.update") || "Update Profile") : t("profiles.form.save")}
          </button>
        </div>

        <div className="kane-card kane-grain space-y-3 p-5">
          <div className="text-sm font-semibold text-[var(--kane-walnut)]">{t("profiles.section.bind")}</div>
          <select
            className={inputClass}
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>
                {a.display_name} ({a.agent_id})
              </option>
            ))}
          </select>
          <select
            className={inputClass}
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
          >
            <option value="">{t("profiles.bind.select_placeholder")}</option>
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.name} {p.is_default ? `[${t("profiles.form.default_label")}]` : ""} - {p.provider} - {p.model}
              </option>
            ))}
          </select>
          <div className="text-xs text-[var(--kane-muted)]">
            {t("profiles.bind.selected")} {agentBindingLabel || "-"}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !selectedProfileId}
              onClick={onBind}
              className={secondaryButton}
            >
              {t("profiles.bind.bind_btn")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onInspectAgent}
              className={secondaryButton}
            >
              {t("profiles.bind.inspect_btn")}
            </button>
          </div>
        </div>
      </div>

      <div className="kane-card kane-grain p-5">
        <div className="text-sm font-semibold text-[var(--kane-walnut)]">{t("profiles.section.list")}</div>
        <div className="mt-3 space-y-2">
          {profiles.length ? (
            profiles.map((p) => (
              <div key={p.profile_id} className="rounded-md border border-[var(--kane-border)] bg-white/45 p-3 text-sm">
                <div className="font-semibold text-[var(--kane-walnut)]">
                  {p.name} {p.is_default ? `(${t("profiles.form.default_label")})` : ""}
                </div>
                <div className="mt-1 font-mono text-xs text-[var(--kane-muted)]">
                  {p.profile_id} - {p.provider} - {p.base_url} - {p.model} - api key hidden
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    data-testid={`api-profile-test-${p.profile_id}`}
                    onClick={() => void onTestProfile(p.profile_id)}
                    className="rounded-md border border-emerald-200 bg-[var(--kane-moss-soft)] px-3 py-1.5 text-xs text-[var(--kane-moss)] disabled:opacity-50"
                  >
                    {t("profiles.list.test_connectivity")}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => startEdit(p)}
                    className="rounded-md border border-[var(--kane-border)] bg-white/55 px-3 py-1.5 text-xs text-[var(--kane-walnut)] disabled:opacity-50"
                  >
                    {t("profiles.list.edit") || "Edit"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm(`${t("profiles.list.delete_confirm") || "Delete this profile?"}\n\n${p.name}\n${p.profile_id}`)) {
                        onDelete(p.profile_id).catch(() => undefined);
                      }
                    }}
                    className="rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs text-rose-700 disabled:opacity-50"
                  >
                    {t("profiles.list.delete") || "Delete"}
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-[var(--kane-muted)]">{t("profiles.list.empty")}</div>
          )}
        </div>
      </div>

      {log ? (
        <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap rounded-md bg-[var(--kane-walnut)] p-3 text-xs text-[var(--kane-topbar-text)]">
          {log}
        </pre>
      ) : null}
    </section>
  );
}
