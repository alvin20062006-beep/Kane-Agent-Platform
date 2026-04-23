"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { Agent } from "@/lib/octopus-types";

import { ADD_TEMPLATES, type AddTemplate } from "./agent-templates";

function capsForRegister(cap: Record<string, boolean>): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const [k, v] of Object.entries(cap)) {
    if (typeof v === "boolean") out[k] = v;
  }
  return out;
}

export default function AgentsAddPage() {
  const t = useT();
  const [templateId, setTemplateId] = useState<string>(ADD_TEMPLATES[0].id);
  const tpl = useMemo(
    () => ADD_TEMPLATES.find((t) => t.id === templateId) ?? ADD_TEMPLATES[0],
    [templateId]
  );

  const [agentId, setAgentId] = useState("");
  const [displayName, setDisplayName] = useState(tpl.defaults.display_name);
  const [registerBridge, setRegisterBridge] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const applyTemplate = useCallback((t: AddTemplate) => {
    setDisplayName(t.defaults.display_name);
  }, []);

  const onTemplateChange = (id: string) => {
    setTemplateId(id);
    const t = ADD_TEMPLATES.find((x) => x.id === id);
    if (t) applyTemplate(t);
  };

  const submit = async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    setCreatedId(null);
    try {
      const body = {
        agent_id: agentId.trim() || null,
        display_name: displayName.trim() || tpl.defaults.display_name,
        type: tpl.defaults.type,
        adapter_id: tpl.defaults.adapter_id,
        integration_mode: tpl.defaults.integration_mode,
        integration_channels: tpl.defaults.integration_channels,
        control_depth: tpl.defaults.control_depth,
        capabilities: tpl.defaults.capabilities,
        control_plane: { ...tpl.defaults.control_plane },
      };
      const res = await apiPost<{ data: Agent }>("/agents", body);
      const aid = res.data.agent_id;
      setCreatedId(aid);
      if (registerBridge) {
        await apiPost("/local-bridge/register", {
          agent_id: aid,
          display_name: res.data.display_name,
          adapter_id: res.data.adapter_id,
          capabilities: capsForRegister(res.data.capabilities ?? {}),
          status: "online",
        });
        setMsg(t("agents_add.msg_created_registered"));
      } else {
        setMsg(t("agents_add.msg_created_no_bridge"));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <PageTitle
        title={t("agents_add.title")}
        subtitle={t("agents_add.subtitle")}
      />

      <BetaNotice note={t("agents_add.beta_notice")} />

      <div className="flex flex-wrap gap-3 text-sm">
        <Link href="/agent-fleet" className="text-zinc-700 underline">
          ← {t("nav.agents")}
        </Link>
        <Link href="/local-bridge" className="text-zinc-700 underline">
          {t("agents_add.bridge_wizard")}
        </Link>
      </div>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-4" data-testid="agents-add-form">
        <div>
          <label className="text-xs font-medium text-zinc-600">{t("agents_add.template_type")}</label>
          <select
            data-testid="agents-add-template"
            className="mt-1 w-full max-w-xl rounded-md border border-zinc-200 px-3 py-2 text-sm"
            value={templateId}
            onChange={(e) => onTemplateChange(e.target.value)}
          >
            {ADD_TEMPLATES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </div>

        <div
          className="rounded-md bg-amber-50 border border-amber-100 p-3 text-sm text-amber-950"
          data-testid="agents-add-honesty"
        >
          <div className="font-medium text-xs text-amber-900">{t("agents_add.honesty")}</div>
          <p className="mt-1">{tpl.honesty}</p>
          <p className="mt-2 text-xs text-amber-900/90">{tpl.summary}</p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-xs text-zinc-600">{t("agents_add.agent_id_label")}</label>
            <input
              data-testid="agents-add-id"
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              placeholder={t("agents_add.agent_id_placeholder")}
            />
          </div>
          <div>
            <label className="text-xs text-zinc-600">{t("agents_add.display_name")}</label>
            <input
              className="mt-1 w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm text-zinc-700">
          <input
            type="checkbox"
            checked={registerBridge}
            onChange={(e) => setRegisterBridge(e.target.checked)}
          />
          {t("agents_add.register_bridge")}
        </label>

        <button
          type="button"
          disabled={busy}
          data-testid="agents-add-submit"
          onClick={() => submit()}
          className="rounded-md bg-[var(--octo-royal-blue)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? t("agents_add.submitting") : t("agents_add.save")}
        </button>

        {err ? (
          <div className="text-sm text-red-700" data-testid="agents-add-error">
            {err}
          </div>
        ) : null}
        {msg ? (
          <div className="text-sm text-emerald-800" data-testid="agents-add-result">
            {msg}
          </div>
        ) : null}
        {createdId ? (
          <div className="text-sm" data-testid="agents-add-created-link">
            {t("agents_add.go_config")}{" "}
            <Link className="font-medium underline" href={`/agent-fleet/${encodeURIComponent(createdId)}`}>
              /agent-fleet/{createdId}
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
