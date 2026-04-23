"use client";

import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost } from "@/lib/api";
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

export function ApiProfilesClient() {
  const t = useT();
  const [profiles, setProfiles] = useState<ApiProfile[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("octopus_builtin");
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [octopusBinding, setOctopusBinding] = useState<OctopusBindingStatus | null>(null);
  const [activateProfileId, setActivateProfileId] = useState<string>("");
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
    // Load current octopus_builtin binding
    try {
      const detail = await apiGet<{ api_profile: OctopusBindingStatus }>("/agents/octopus_builtin");
      setOctopusBinding(detail.api_profile ?? null);
      if (detail.api_profile?.binding?.profile_id) {
        setActivateProfileId(detail.api_profile.binding.profile_id);
      }
    } catch {
      // octopus_builtin may not exist yet
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
        ...form,
        api_key: form.api_key || null,
      });
      setLog(JSON.stringify(res, null, 2));
      setForm((f) => ({ ...f, api_key: "" }));
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

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-4">
      <div className="rounded-lg border-2 border-zinc-900 bg-zinc-50 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold">{t("profiles.section.activation")}</span>
          {octopusBinding?.profile ? (
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700 font-medium">
              {t("profiles.activation.active")
                .replace("{name}", octopusBinding.profile.name)
                .replace("{model}", octopusBinding.profile.model)}
            </span>
          ) : (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700 font-medium">
              {t("profiles.activation.inactive")}
            </span>
          )}
        </div>
        <p className="text-xs text-zinc-500">{t("profiles.activation.hint")}</p>
        {profiles.length === 0 ? (
          <p className="text-xs text-zinc-400">{t("profiles.activation.empty")}</p>
        ) : (
          <div className="flex gap-2 flex-wrap">
            <select
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
              value={activateProfileId}
              onChange={(e) => setActivateProfileId(e.target.value)}
            >
              <option value="">{t("profiles.activation.select_placeholder")}</option>
              {profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.name} — {p.provider} — {p.model}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={busy || !activateProfileId}
              onClick={onActivateOctopus}
              className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {t("profiles.activation.activate")}
            </button>
          </div>
        )}
      </div>

      <div className="text-sm font-semibold">{t("profiles.section.main")}</div>
      <div className="text-xs text-zinc-500">{t("profiles.intro")}</div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-md border border-zinc-200 p-3 space-y-2">
          <div className="text-sm font-medium">{t("profiles.section.new")}</div>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
            placeholder={t("profiles.form.name_ph")}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <div className="grid gap-2 md:grid-cols-2">
            <select
              className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={form.provider}
              onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value as ApiProfile["provider"] }))}
            >
              <option value="openai_compatible">openai_compatible</option>
              <option value="anthropic_compatible">anthropic_compatible</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
              />
              {t("profiles.form.default_label")}
            </label>
          </div>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            placeholder={t("profiles.form.base_ph")}
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
          />
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            placeholder={t("profiles.form.model_ph")}
            value={form.model}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
          />
          <input
            type="password"
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            placeholder={t("profiles.form.key_ph")}
            value={form.api_key}
            onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
          />
          <button
            type="button"
            disabled={busy || !form.name.trim()}
            onClick={onCreate}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {t("profiles.form.save")}
          </button>
        </div>

        <div className="rounded-md border border-zinc-200 p-3 space-y-2">
          <div className="text-sm font-medium">{t("profiles.section.bind")}</div>
          <select
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
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
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
          >
            <option value="">{t("profiles.bind.select_placeholder")}</option>
            {profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {p.name} {p.is_default ? `[${t("profiles.form.default_label")}]` : ""} — {p.provider} — {p.model}
              </option>
            ))}
          </select>
          <div className="text-xs text-zinc-500">
            {t("profiles.bind.selected")} {agentBindingLabel || "—"}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !selectedProfileId}
              onClick={onBind}
              className="rounded-md border border-zinc-200 px-3 py-2 text-sm disabled:opacity-50"
            >
              {t("profiles.bind.bind_btn")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onInspectAgent}
              className="rounded-md border border-zinc-200 px-3 py-2 text-sm disabled:opacity-50"
            >
              {t("profiles.bind.inspect_btn")}
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-zinc-200 p-3">
        <div className="text-sm font-medium">{t("profiles.section.list")}</div>
        <div className="mt-2 space-y-2">
          {profiles.length ? (
            profiles.map((p) => (
              <div key={p.profile_id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="font-medium">
                  {p.name}{" "}
                  {p.is_default ? `(${t("profiles.form.default_label")})` : ""}
                </div>
                <div className="mt-1 text-xs text-zinc-500 font-mono">
                  {p.profile_id} • {p.provider} • {p.base_url} • {p.model} • api_key={p.api_key ?? "null"}
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-zinc-500">{t("profiles.list.empty")}</div>
          )}
        </div>
      </div>

      {log ? (
        <pre className="max-h-[260px] overflow-auto whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs text-zinc-100">
          {log}
        </pre>
      ) : null}
    </section>
  );
}

