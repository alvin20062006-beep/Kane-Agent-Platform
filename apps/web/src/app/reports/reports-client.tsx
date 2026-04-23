"use client";

import Link from "next/link";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

type Report = {
  report_id: string;
  type: string;
  title: string;
  created_at: string;
  content: string;
  is_mock: boolean;
};

export function ReportsClient({
  items,
  errorText,
}: {
  items: Report[] | null;
  errorText: string | null;
}) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("reports.title")} subtitle={t("reports.subtitle")} />
      <BetaNotice note={t("reports.beta_notice")} />

      {errorText ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorText}
        </div>
      ) : null}

      {items ? (
        <div className="space-y-3">
          {items.map((report) => (
            <div key={report.report_id} className="rounded-lg border border-zinc-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">{report.title}</div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {report.report_id} • {report.type} • {t("reports.persisted")} {String(!report.is_mock)}
                  </div>
                </div>
                <div className="text-xs text-zinc-500">{report.created_at}</div>
              </div>
              <div className="mt-3 whitespace-pre-wrap text-sm text-zinc-700">{report.content}</div>
              <div className="mt-4">
                <Link
                  href={`/reports/${encodeURIComponent(report.report_id)}`}
                  className="inline-block rounded-md border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50"
                >
                  {t("reports.open")}
                </Link>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

