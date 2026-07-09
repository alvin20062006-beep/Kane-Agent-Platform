"use client";

import Link from "next/link";

import { useT } from "@/lib/i18n/LocaleProvider";

export function FleetHeader() {
  const t = useT();
  return (
    <div className="kane-page-header flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="kane-page-title">
          {t("agents.title")}
        </h1>
        <p className="kane-page-subtitle">{t("agents.subtitle")}</p>
      </div>
      <div className="flex gap-2 text-[var(--kane-caption-size)]">
        <Link
          className="kane-button-secondary inline-flex items-center rounded-[var(--kane-radius-control)] px-3.5 py-2 font-medium hover:bg-white"
          href="/local-bridge"
        >
          {t("agents.bridge_wizard")}
        </Link>
        <Link
          className="kane-button-primary inline-flex items-center rounded-[var(--kane-radius-control)] px-3.5 py-2 font-semibold hover:opacity-95"
          href="/agents/add"
        >
          {t("agents.add")}
        </Link>
      </div>
    </div>
  );
}
