"use client";

import Link from "next/link";

import { BetaNotice } from "@/components/beta-notice";
import { JsonCard } from "@/components/json-card";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

export function ReportDetailClient({
  reportId,
  data,
  errorText,
}: {
  reportId: string;
  data: unknown | null;
  errorText: string | null;
}) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between gap-3">
        <PageTitle title={t("report_detail.title")} subtitle={t("report_detail.subtitle", reportId)} />
        <Link
          href="/reports"
          className="text-sm rounded-md border border-zinc-200 px-3 py-2 hover:bg-zinc-50"
        >
          {t("report_detail.back")}
        </Link>
      </div>

      <BetaNotice note={t("report_detail.beta_notice")} />

      {errorText ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorText}
        </div>
      ) : null}

      {data ? (
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">{t("report_detail.payload")}</div>
          <div className="mt-3">
            <JsonCard data={data} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

