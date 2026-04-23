"use client";

import Link from "next/link";

import { useT } from "@/lib/i18n/LocaleProvider";

export function FleetHeader() {
  const t = useT();
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900">
          {t("agents.title")}
        </h1>
        <p className="mt-1 text-sm text-zinc-600">{t("agents.subtitle")}</p>
      </div>
      <div className="flex gap-2 text-sm">
        <Link
          className="inline-flex items-center rounded-full border border-zinc-200 bg-white px-4 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
          href="/local-bridge"
        >
          {t("agents.bridge_wizard")}
        </Link>
        <Link
          className="inline-flex items-center rounded-full px-4 py-1.5 text-xs font-semibold text-white hover:opacity-90"
          style={{ background: "var(--octo-royal-blue)" }}
          href="/agents/add"
        >
          {t("agents.add")}
        </Link>
      </div>
    </div>
  );
}
