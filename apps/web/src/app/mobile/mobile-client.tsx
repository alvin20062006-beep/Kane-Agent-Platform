"use client";

import Link from "next/link";

import { BetaNotice } from "@/components/beta-notice";
import { PageTitle } from "@/components/page-title";
import { useT } from "@/lib/i18n/LocaleProvider";

export function MobileClient() {
  const t = useT();
  return (
    <div className="space-y-6 p-6">
      <PageTitle title={t("mobile.title")} subtitle={t("mobile.subtitle")} />

      <BetaNotice note={t("mobile.beta_notice")} />

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("mobile.scope_title")}</div>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-700">
          <li>{t("mobile.scope_1")}</li>
          <li>{t("mobile.scope_2")}</li>
          <li>{t("mobile.scope_3")}</li>
        </ul>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("mobile.quick_actions")}</div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {[
            [t("nav.cockpit"), "/cockpit"],
            [t("nav.tasks"), "/tasks"],
            [t("nav.agents"), "/agent-fleet"],
            [t("topbar.watchdog"), "/watchdog"],
          ].map(([label, href]) => (
            <Link
              key={href}
              href={href}
              className="rounded-md border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50"
            >
              {label}
            </Link>
          ))}
        </div>
        <div className="mt-3 text-xs text-zinc-500">{t("mobile.todo")}</div>
      </section>
    </div>
  );
}

