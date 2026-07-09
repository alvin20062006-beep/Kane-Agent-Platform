"use client";

import { useMemo, useState } from "react";

import { ProductNotice } from "@/components/product-notice";
import { PageTitle } from "@/components/page-title";
import { apiGet, apiPost } from "@/lib/api";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { AdvisorSuggestion, PolicyExplanation } from "@/lib/octopus-types";

type ExecutionPolicy = {
  policy_id: string;
  scope: "global" | "agent" | "skill" | "account";
  target_id?: string | null;
  mode: "auto" | "notify" | "confirm";
  note?: string | null;
  is_draft: boolean;
};

function renderPolicyPreview(suggestion: AdvisorSuggestion) {
  const preview = suggestion.policy_preview;
  if (!preview) return null;
  return (
    <div className="mt-3 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700">
      <div className="font-medium text-zinc-800">Draft preview</div>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        <div>target_scope={preview.target_scope}</div>
        <div>target_label={preview.target_label}</div>
        <div>current_effective_mode={preview.current_effective_mode}</div>
        <div>current_default_execution_policy={preview.current_default_execution_policy ?? "n/a"}</div>
        <div>suggested_mode={preview.suggested_mode ?? "n/a"}</div>
        <div>policy_source={preview.policy_source ?? "n/a"}</div>
        <div>matched_policy_id={preview.matched_policy_id ?? "none"}</div>
        <div>precedence={(preview.precedence ?? []).join(" -> ") || "n/a"}</div>
      </div>
      {preview.reason ? <div className="mt-2 text-zinc-600">{preview.reason}</div> : null}
      {preview.suggested_change ? (
        <div className="mt-2 rounded-md bg-white px-2 py-1 text-zinc-700">
          suggested change: {preview.suggested_change}
        </div>
      ) : null}
    </div>
  );
}
export function PoliciesClient({
  items,
  suggestions,
  errorText,
}: {
  items: ExecutionPolicy[] | null;
  suggestions: AdvisorSuggestion[];
  errorText: string | null;
}) {
  const t = useT();
  const [policies, setPolicies] = useState(items ?? []);
  const [policyId, setPolicyId] = useState("pol_runtime_confirm");
  const [scope, setScope] = useState<ExecutionPolicy["scope"]>("global");
  const [targetId, setTargetId] = useState("");
  const [mode, setMode] = useState<ExecutionPolicy["mode"]>("confirm");
  const [note, setNote] = useState("enforced policy");
  const [draftOnly, setDraftOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [previewScope, setPreviewScope] = useState<ExecutionPolicy["scope"]>("global");
  const [previewTargetId, setPreviewTargetId] = useState("");
  const [preview, setPreview] = useState<PolicyExplanation | null>(null);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);

  const summary = useMemo(
    () => ({
      total: policies.length,
      enforced: policies.filter((policy) => !policy.is_draft).length,
      global: policies.filter((policy) => policy.scope === "global").length,
      confirm: policies.filter((policy) => policy.mode === "confirm").length,
    }),
    [policies]
  );

  const savePolicy = async () => {
    setBusy(true);
    setSaveMessage(null);
    try {
      const response = await apiPost<{ data: ExecutionPolicy }>("/policies", {
        policy_id: policyId.trim(),
        scope,
        target_id: targetId.trim() || null,
        mode,
        note: note.trim() || null,
        is_draft: draftOnly,
      });
      const next = [...policies.filter((policy) => policy.policy_id !== response.data.policy_id), response.data];
      next.sort((left, right) => left.policy_id.localeCompare(right.policy_id));
      setPolicies(next);
      setSaveMessage(`Saved ${response.data.policy_id}`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const explainPolicy = async () => {
    setBusy(true);
    setPreviewMessage(null);
    try {
      const query = new URLSearchParams({
        scope: previewScope,
        ...(previewTargetId.trim() ? { target_id: previewTargetId.trim() } : {}),
      });
      const response = await apiGet<{ data: PolicyExplanation }>(`/policies/explain?${query.toString()}`);
      setPreview(response.data);
      setPreviewMessage(`Loaded effective policy for ${previewScope}${previewTargetId.trim() ? `:${previewTargetId.trim()}` : ""}`);
    } catch (error) {
      setPreviewMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("policies.title")} subtitle={t("policies.subtitle")} />

      <ProductNotice note={t("policies.notice")} />

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-500">Policies</div>
          <div className="mt-2 text-2xl font-semibold">{summary.total}</div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-500">Enforced</div>
          <div className="mt-2 text-2xl font-semibold">{summary.enforced}</div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-500">Global</div>
          <div className="mt-2 text-2xl font-semibold">{summary.global}</div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-xs text-zinc-500">Confirm gates</div>
          <div className="mt-2 text-2xl font-semibold">{summary.confirm}</div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_1.9fr]">
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">Create or update policy</div>
          <div className="mt-3 grid gap-3">
            <label className="space-y-1">
              <span className="text-xs text-zinc-600">policy_id</span>
              <input
                data-testid="policy-id-input"
                className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                value={policyId}
                onChange={(event) => setPolicyId(event.target.value)}
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-zinc-600">scope</span>
              <select
                data-testid="policy-scope-select"
                className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                value={scope}
                onChange={(event) => setScope(event.target.value as ExecutionPolicy["scope"])}
              >
                <option value="global">global</option>
                <option value="agent">agent</option>
                <option value="skill">skill</option>
                <option value="account">account</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs text-zinc-600">target_id</span>
              <input
                data-testid="policy-target-input"
                className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                value={targetId}
                onChange={(event) => setTargetId(event.target.value)}
                placeholder="optional"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs text-zinc-600">mode</span>
              <select
                data-testid="policy-mode-select"
                className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                value={mode}
                onChange={(event) => setMode(event.target.value as ExecutionPolicy["mode"])}
              >
                <option value="auto">auto</option>
                <option value="notify">notify</option>
                <option value="confirm">confirm</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-xs text-zinc-600">note</span>
              <textarea
                className="min-h-[96px] w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={draftOnly}
                onChange={(event) => setDraftOnly(event.target.checked)}
              />
              {t("policies.save_draft_only")}
            </label>
            <button
              data-testid="policy-save-button"
              type="button"
              disabled={busy || !policyId.trim()}
              onClick={savePolicy}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {busy ? "Saving..." : "Save policy"}
            </button>
            {saveMessage ? (
              <div data-testid="policy-save-message" className="text-sm text-zinc-700">
                {saveMessage}
              </div>
            ) : null}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm">
            <div className="font-semibold">Policy precedence</div>
            <div className="mt-2 text-zinc-700">
              Runtime keeps policy resolution lightweight and explicit:
              <div className="mt-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-xs">
                agent / skill / account - global - fallback default
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm">
            <div className="font-semibold">Explain effective policy</div>
            <div className="mt-3 grid gap-3 md:grid-cols-[0.8fr_1.2fr_auto]">
              <label className="space-y-1">
                <span className="text-xs text-zinc-600">scope</span>
                <select
                  data-testid="policy-preview-scope-select"
                  className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm"
                  value={previewScope}
                  onChange={(event) => setPreviewScope(event.target.value as ExecutionPolicy["scope"])}
                >
                  <option value="global">global</option>
                  <option value="agent">agent</option>
                  <option value="skill">skill</option>
                  <option value="account">account</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-zinc-600">target_id</span>
                <input
                  data-testid="policy-preview-target-input"
                  className="w-full rounded-md border border-zinc-200 px-3 py-2 text-sm font-mono"
                  value={previewTargetId}
                  onChange={(event) => setPreviewTargetId(event.target.value)}
                  placeholder={previewScope === "global" ? "optional" : "required for scoped previews"}
                />
              </label>
              <div className="flex items-end">
                <button
                  data-testid="policy-preview-button"
                  type="button"
                  disabled={busy}
                  onClick={explainPolicy}
                  className="rounded-md border border-zinc-200 px-3 py-2 text-sm font-medium disabled:opacity-50"
                >
                  Explain
                </button>
              </div>
            </div>
            {previewMessage ? <div data-testid="policy-preview-message" className="mt-3 text-xs text-zinc-500">{previewMessage}</div> : null}
            {preview ? (
              <div data-testid="policy-preview-card" className="mt-3 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700">
                <div>effective_mode={preview.effective_mode}</div>
                <div>policy_source={preview.policy_source}</div>
                <div>matched_policy_id={preview.matched_policy_id ?? "none"}</div>
                <div>precedence={preview.precedence.join(" -> ")}</div>
                <div className="mt-2 text-zinc-600">{preview.reason ?? "No extra explanation available."}</div>
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm">
            <div className="font-semibold">{t("policies.quick_enable")}</div>
            <div className="mt-2 text-zinc-700">{t("policies.quick_enable_hint")}</div>
            <pre className="mt-2 overflow-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100 whitespace-pre-wrap">
{`$body=@{ policy_id='pol_global_enforced'; scope='global'; mode='confirm'; note='enforced'; is_draft=$false } | ConvertTo-Json -Compress
$body | curl.exe -s -X POST http://127.0.0.1:8000/policies -H \"content-type: application/json\" --data-binary '@-'`}
            </pre>
          </div>

          <div data-testid="policy-advisor-card" className="rounded-lg border border-zinc-200 bg-white p-4 text-sm">
            <div className="font-semibold">Policy / Skill Suggestions</div>
            <div className="mt-2 space-y-3">
              {suggestions.length ? (
                suggestions.map((suggestion) => (
                  <div key={suggestion.suggestion_id} className="rounded-md border border-zinc-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="font-medium">{suggestion.title}</div>
                      <div className="text-xs text-zinc-500">
                        {suggestion.severity} / {suggestion.status} / confidence={suggestion.confidence ?? "low"}
                      </div>
                    </div>
                    <div className="mt-2 text-zinc-700">{suggestion.summary}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-zinc-500">
                      <span className="rounded-full border border-zinc-200 px-2 py-1">
                        occurrences={suggestion.occurrence_count ?? 1}
                      </span>
                      <span className="rounded-full border border-zinc-200 px-2 py-1">
                        affected_targets={suggestion.affected_targets ?? 1}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-zinc-500">
                      next: {suggestion.recommended_action}
                    </div>
                    {renderPolicyPreview(suggestion)}
                  </div>
                ))
              ) : (
                <div className="text-sm text-zinc-500">No policy or skill suggestions have been generated yet.</div>
              )}
            </div>
          </div>

          {errorText ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {errorText}
            </div>
          ) : null}

          <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
            <table data-testid="policies-table" className="w-full text-sm">
              <thead className="bg-zinc-50 text-zinc-600">
                <tr>
                  <th className="text-left font-medium px-4 py-3">{t("policies.col.policy")}</th>
                  <th className="text-left font-medium px-4 py-3">{t("policies.col.scope")}</th>
                  <th className="text-left font-medium px-4 py-3">{t("policies.col.mode")}</th>
                  <th className="text-left font-medium px-4 py-3">{t("policies.col.note")}</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((policy) => (
                  <tr key={policy.policy_id} className="border-t border-zinc-200">
                    <td className="px-4 py-3">
                      <div className="font-medium">{policy.policy_id}</div>
                      <div className="text-xs text-zinc-500">
                        {policy.is_draft ? t("policies.label_draft") : t("policies.label_enforced")}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {policy.scope}
                      {policy.target_id ? (
                        <div className="text-xs text-zinc-500">target: {policy.target_id}</div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs rounded-full border border-zinc-200 px-2 py-1">{policy.mode}</span>
                    </td>
                    <td className="px-4 py-3 text-zinc-700">{policy.note ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
