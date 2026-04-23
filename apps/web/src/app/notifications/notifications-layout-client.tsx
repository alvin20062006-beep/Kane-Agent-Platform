"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

export function NotificationsLayoutClient({ children }: { children: ReactNode }) {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("notif.title")} subtitle={t("notif.subtitle")} />

      <BetaNotice note={t("notif.beta_notice")} />

      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-700">
        <Link href="/settings" className="text-zinc-900 underline underline-offset-2">
          {t("notif.back_settings")}
        </Link>
        <span className="mx-2 text-zinc-300">|</span>
        <span>
          {t("notif.api_line")}{" "}
          <code className="rounded bg-zinc-50 px-1 text-xs">GET /notifications/channels</code>
          {", "}
          <code className="rounded bg-zinc-50 px-1 text-xs">POST /notifications/channels</code>
        </span>
      </div>

      {children}
    </div>
  );
}
