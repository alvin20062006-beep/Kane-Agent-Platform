"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

import { apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { Agent, LocalBridgeAgentState } from "@/lib/octopus-types";

export type ConnectionsCredential = {
  credential_id: string;
  account_id: string;
  provider: string;
  credential_type: string;
  status: string;
  created_at?: string;
  masked_hint?: string | null;
};

export type ConnectionsAccount = {
  account_id: string;
  provider: string;
  display_name: string;
  credential_type: string;
  scopes: string[];
  status: string;
};

type Tab = "credentials" | "accounts" | "adapters";

type Props = {
  credentials: ConnectionsCredential[];
  accounts: ConnectionsAccount[];
  agents: Agent[];
  bridgeAgents: LocalBridgeAgentState[];
};

export function ConnectionsClient({
  credentials,
  accounts,
  agents,
  bridgeAgents,
}: Props) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const initial = (sp.get("tab") as Tab) || "credentials";
  const [tab, setTab] = useState<Tab>(initial);
  const [creds, setCreds] = useState<ConnectionsCredential[]>(credentials);
  const [showNew, setShowNew] = useState<boolean>(sp.get("new") === "1");

  const setTabAndUrl = (next: Tab) => {
    setTab(next);
    const params = new URLSearchParams(Array.from(sp.entries()));
    params.set("tab", next);
    params.delete("new");
    router.replace(`${pathname}?${params.toString()}`);
    setShowNew(false);
  };

  const openNewPanel = () => {
    setShowNew(true);
    const params = new URLSearchParams(Array.from(sp.entries()));
    params.set("tab", "credentials");
    params.set("new", "1");
    router.replace(`${pathname}?${params.toString()}`);
  };

  const closeNewPanel = () => {
    setShowNew(false);
    const params = new URLSearchParams(Array.from(sp.entries()));
    params.delete("new");
    router.replace(`${pathname}?${params.toString()}`);
  };

  const tabs: Array<{ id: Tab; labelKey: string; count: number }> = useMemo(
    () => [
      { id: "credentials", labelKey: "connections.tab.credentials", count: creds.length },
      { id: "accounts", labelKey: "connections.tab.accounts", count: accounts.length },
      { id: "adapters", labelKey: "connections.tab.adapters", count: agents.length },
    ],
    [creds.length, accounts.length, agents.length]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4 border-b border-zinc-200">
        <div className="flex gap-4">
          {tabs.map((it) => {
            const active = tab === it.id;
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => setTabAndUrl(it.id)}
                className={`-mb-px border-b-2 px-1 pb-2 text-sm transition-colors ${
                  active
                    ? "border-zinc-900 font-semibold text-zinc-900"
                    : "border-transparent text-zinc-500 hover:text-zinc-800"
                }`}
              >
                {t(it.labelKey)}
                <span className="ml-1 text-xs text-zinc-400">({it.count})</span>
              </button>
            );
          })}
        </div>
        <div className="flex gap-2 pb-2">
          {tab === "credentials" && (
            <button
              type="button"
              onClick={() => (showNew ? closeNewPanel() : openNewPanel())}
              className="rounded-md px-3 py-1.5 text-xs font-semibold text-white"
              style={{ backgroundColor: "var(--octo-royal-blue)" }}
            >
              {showNew ? t("action.cancel") : t("connections.add_credential")}
            </button>
          )}
          {tab === "adapters" && (
            <Link
              href="/agents/add"
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white"
            >
              {t("agents.add")}
            </Link>
          )}
        </div>
      </div>

      {tab === "credentials" && showNew && (
        <NewCredentialPanel
          onCreated={(c) => {
            setCreds((prev) => [c, ...prev]);
            closeNewPanel();
          }}
          onCancel={closeNewPanel}
        />
      )}

      {tab === "credentials" && (
        <div className="rounded-lg border border-zinc-200 bg-white">
          {creds.length === 0 ? (
            <div className="p-6 text-sm text-zinc-500">{t("connections.empty")}</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.credential")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.provider")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.type")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {creds.map((c) => (
                  <tr key={c.credential_id} className="border-t border-zinc-200">
                    <td className="px-4 py-3">
                      <div className="font-medium">{c.credential_id}</div>
                      <div className="text-xs text-zinc-500">
                        {t("connections.col.account")}: {c.account_id}
                      </div>
                    </td>
                    <td className="px-4 py-3">{c.provider}</td>
                    <td className="px-4 py-3">{c.credential_type}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full border border-zinc-200 px-2 py-1 text-xs">
                        {c.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "accounts" && (
        <div className="space-y-3">
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            {t("connections.accounts.beta_notice")}
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white">
          {accounts.length === 0 ? (
            <div className="p-6 text-sm text-zinc-500">{t("connections.accounts.empty")}</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.account")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.provider")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.type")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.account_id} className="border-t border-zinc-200">
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.display_name}</div>
                      <div className="text-xs text-zinc-500">{a.account_id}</div>
                      <div className="mt-1 text-xs text-zinc-600">
                        {t("connections.scopes")}: {a.scopes.length ? a.scopes.join(", ") : "—"}
                      </div>
                    </td>
                    <td className="px-4 py-3">{a.provider}</td>
                    <td className="px-4 py-3">{a.credential_type}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full border border-zinc-200 px-2 py-1 text-xs">
                        {a.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          </div>
        </div>
      )}

      {tab === "adapters" && (
        <div className="rounded-lg border border-zinc-200 bg-white">
          {agents.length === 0 ? (
            <div className="p-6 text-sm text-zinc-500">{t("connections.empty")}</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">{t("agents.adapter")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.agent")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.status")}</th>
                  <th className="px-4 py-3 text-left font-medium">{t("connections.col.bridge")}</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => {
                  const bridgeState = bridgeAgents.find(
                    (item) => item.agent_id === agent.agent_id
                  );
                  return (
                    <tr key={agent.agent_id} className="border-t border-zinc-200">
                      <td className="px-4 py-3">{agent.adapter_id ?? "builtin_octopus"}</td>
                      <td className="px-4 py-3">
                        <div className="font-medium">{agent.display_name}</div>
                        <div className="text-xs text-zinc-500">{agent.agent_id}</div>
                      </td>
                      <td className="px-4 py-3">{agent.status}</td>
                      <td className="px-4 py-3">
                        {bridgeState ? (
                          <div>
                            <div>{bridgeState.status}</div>
                            <div className="text-xs text-zinc-500">
                              {t("connections.bridge.seen")} {bridgeState.last_seen_at}
                            </div>
                          </div>
                        ) : (
                          <span className="text-zinc-500">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function NewCredentialPanel({
  onCreated,
  onCancel,
}: {
  onCreated: (c: ConnectionsCredential) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [accountId, setAccountId] = useState("");
  const [provider, setProvider] = useState("github");
  const [credentialType, setCredentialType] = useState("api_key");
  const [credentialRef, setCredentialRef] = useState("");
  const [secret, setSecret] = useState("");
  const [maskedHint, setMaskedHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!accountId.trim() || !secret.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await apiPost<{ data: ConnectionsCredential }>("/credentials", {
        account_id: accountId.trim(),
        provider: provider.trim(),
        credential_type: credentialType.trim(),
        secret_material: secret,
        credential_ref: credentialRef.trim() || null,
        masked_hint: maskedHint.trim() || null,
      });
      onCreated(resp.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">{t("connections.new.title")}</div>
          <div className="text-xs text-zinc-500">{t("connections.new.hint")}</div>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-zinc-500 hover:text-zinc-800"
        >
          {t("action.cancel")}
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs text-zinc-600">{t("connections.field.account_id")}</span>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            placeholder="acct_github_main"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-zinc-600">{t("connections.field.provider")}</span>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            placeholder="github / openai / google"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-zinc-600">{t("connections.field.credential_type")}</span>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={credentialType}
            onChange={(e) => setCredentialType(e.target.value)}
            placeholder="api_key / oauth / bearer"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-zinc-600">{t("connections.field.credential_ref")}</span>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={credentialRef}
            onChange={(e) => setCredentialRef(e.target.value)}
            placeholder="cred_github_main"
          />
        </label>
        <label className="space-y-1 md:col-span-2">
          <span className="text-xs text-zinc-600">{t("connections.field.secret")}</span>
          <input
            type="password"
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="••••••••"
          />
        </label>
        <label className="space-y-1 md:col-span-2">
          <span className="text-xs text-zinc-600">{t("connections.field.masked_hint")}</span>
          <input
            className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
            value={maskedHint}
            onChange={(e) => setMaskedHint(e.target.value)}
            placeholder="ghp_…xxxx"
          />
        </label>
      </div>
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      ) : null}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy || !secret.trim() || !accountId.trim()}
          onClick={save}
          className="rounded-md px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          style={{ backgroundColor: "var(--octo-royal-blue)" }}
        >
          {busy ? t("action.saving") : t("action.save")}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50"
        >
          {t("action.cancel")}
        </button>
      </div>
    </section>
  );
}
