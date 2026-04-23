"use client";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

type ExecutionPolicy = {
  policy_id: string;
  scope: "global" | "agent" | "skill" | "account";
  target_id?: string | null;
  mode: "auto" | "notify" | "confirm";
  note?: string | null;
  is_mock: boolean;
};

export function PoliciesClient({
  items,
  errorText,
}: {
  items: ExecutionPolicy[] | null;
  errorText: string | null;
}) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("policies.title")} subtitle={t("policies.subtitle")} />

      <BetaNotice note={t("policies.beta_notice")} />

      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm">
        <div className="font-semibold">{t("policies.quick_enable")}</div>
        <div className="mt-2 text-zinc-700">{t("policies.quick_enable_hint")}</div>
        <pre className="mt-2 overflow-auto rounded-md bg-zinc-950 p-3 text-xs text-zinc-100 whitespace-pre-wrap">
{`$body=@{ policy_id='pol_global_enforced'; scope='global'; mode='confirm'; note='enforced'; is_mock=$false } | ConvertTo-Json -Compress
$body | curl.exe -s -X POST http://127.0.0.1:8000/policies -H \"content-type: application/json\" --data-binary '@-'`}
        </pre>
      </div>

      {errorText ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorText}
        </div>
      ) : null}

      {items ? (
        <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-zinc-600">
              <tr>
                <th className="text-left font-medium px-4 py-3">{t("policies.col.policy")}</th>
                <th className="text-left font-medium px-4 py-3">{t("policies.col.scope")}</th>
                <th className="text-left font-medium px-4 py-3">{t("policies.col.mode")}</th>
                <th className="text-left font-medium px-4 py-3">{t("policies.col.note")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.policy_id} className="border-t border-zinc-200">
                  <td className="px-4 py-3">
                    <div className="font-medium">{p.policy_id}</div>
                    <div className="text-xs text-zinc-500">is_mock: {String(p.is_mock)}</div>
                  </td>
                  <td className="px-4 py-3">
                    {p.scope}
                    {p.target_id ? (
                      <div className="text-xs text-zinc-500">target: {p.target_id}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs rounded-full border border-zinc-200 px-2 py-1">{p.mode}</span>
                  </td>
                  <td className="px-4 py-3 text-zinc-700">{p.note ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

