"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";

import { ApiProfilesClient } from "./api-profiles-client";
import { SettingsSuspenseFallback } from "./settings-suspense-fallback";

type Category = {
  id: string;
  labelKey: string;
  emoji: string;
  descriptionKey: string;
};

// 5 分类：只保留有独占内容的设置项。技能中心 / Agents / 记忆 / 通知已在主入口，不再重复。
const CATEGORIES: Category[] = [
  { id: "model", labelKey: "settings.cat.model", emoji: "🧠", descriptionKey: "settings.cat_desc.model" },
  {
    id: "connections",
    labelKey: "settings.cat.connections",
    emoji: "🔗",
    descriptionKey: "settings.cat_desc.connections",
  },
  {
    id: "advanced",
    labelKey: "settings.cat.advanced",
    emoji: "⚙️",
    descriptionKey: "settings.cat_desc.advanced",
  },
  { id: "general", labelKey: "settings.cat.general", emoji: "🌐", descriptionKey: "settings.cat_desc.general" },
  { id: "about", labelKey: "settings.cat.about", emoji: "📖", descriptionKey: "settings.cat_desc.about" },
];

function ModelSection() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">{t("settings.model.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">
          {t("settings.model.desc")}
        </p>
      </div>
      <ApiProfilesClient />
    </div>
  );
}

function ConnectionsSection() {
  const t = useT();
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{t("settings.connections.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">
          {t("settings.connections.desc")}
        </p>
      </div>
      <div className="flex gap-3 flex-wrap">
        <Link
          href="/connections?tab=credentials"
          className="rounded-lg border border-zinc-200 bg-white p-4 flex-1 min-w-[180px] hover:border-zinc-400 transition-colors"
        >
          <div className="text-sm font-medium">{t("settings.connections.credentials.title")}</div>
          <div className="mt-1 text-xs text-zinc-500">{t("settings.connections.credentials.desc")}</div>
        </Link>
        <Link
          href="/connections?tab=accounts"
          className="rounded-lg border border-zinc-200 bg-white p-4 flex-1 min-w-[180px] hover:border-zinc-400 transition-colors"
        >
          <div className="text-sm font-medium">{t("settings.connections.accounts.title")}</div>
          <div className="mt-1 text-xs text-zinc-500">{t("settings.connections.accounts.desc")}</div>
        </Link>
        <Link
          href="/connections?tab=adapters"
          className="rounded-lg border border-zinc-200 bg-white p-4 flex-1 min-w-[180px] hover:border-zinc-400 transition-colors"
        >
          <div className="text-sm font-medium">{t("settings.connections.adapters.title")}</div>
          <div className="mt-1 text-xs text-zinc-500">{t("settings.connections.adapters.desc")}</div>
        </Link>
      </div>
    </div>
  );
}

function AdvancedSection() {
  const t = useT();
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{t("settings.advanced.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">
          {t("settings.advanced.desc")}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {[
          {
            href: "/local-bridge",
            label: t("settings.advanced.card.bridge.title"),
            desc: t("settings.advanced.card.bridge.desc"),
          },
          {
            href: "/policies",
            label: t("settings.advanced.card.policies.title"),
            desc: t("settings.advanced.card.policies.desc"),
          },
          {
            href: "/agent-adapters",
            label: t("settings.advanced.card.adapters.title"),
            desc: t("settings.advanced.card.adapters.desc"),
          },
          {
            href: "/reports",
            label: t("settings.advanced.card.reports.title"),
            desc: t("settings.advanced.card.reports.desc"),
          },
          {
            href: "/watchdog",
            label: t("settings.advanced.card.watchdog.title"),
            desc: t("settings.advanced.card.watchdog.desc"),
          },
          {
            href: "/mobile",
            label: t("settings.advanced.card.mobile.title"),
            desc: t("settings.advanced.card.mobile.desc"),
          },
        ].map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="rounded-lg border border-zinc-200 bg-white p-4 hover:border-zinc-400 transition-colors"
          >
            <div className="text-sm font-medium">{item.label}</div>
            <div className="mt-1 text-xs text-zinc-500">{item.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function GeneralSection() {
  const t = useT();
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{t("settings.general.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">{t("settings.general.desc")}</p>
      </div>
      <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3 text-sm">
        <div>
          <span className="font-medium">{t("settings.general.api_base")}:</span>
          <code className="ml-2 rounded border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs font-mono">
            {apiBase}
          </code>
        </div>
        <div className="space-y-1.5 text-xs text-zinc-500">
          {[
            ["NEXT_PUBLIC_API_BASE_URL", t("settings.general.env.api_base_url")],
            ["OCTOPUS_LOCAL_BRIDGE_URL", t("settings.general.env.bridge_url")],
            ["OCTOPUS_API_PUBLIC_URL", t("settings.general.env.api_public_url")],
            ["OCTOPUS_BRIDGE_SHARED_SECRET", t("settings.general.env.bridge_secret")],
            ["OCTOPUS_PERSISTENCE / DATABASE_URL", t("settings.general.env.persistence")],
          ].map(([k, v]) => (
            <div key={k}>
              <code>{k}</code> — {v}
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
        <strong>{t("settings.general.beta_title")}</strong>
        {t("settings.general.beta_body")}
      </div>
    </div>
  );
}

function AboutSection() {
  const t = useT();
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold">{t("settings.about.title")}</h2>
        <p className="mt-1 text-xs text-zinc-500">{t("settings.about.desc")}</p>
      </div>
      <div className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3 text-sm">
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            { label: t("settings.about.link.user_guide"), href: "/help/user-guide" },
            { label: t("settings.about.link.beta_limits"), href: "/help/beta-limitations" },
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg border border-zinc-200 p-3 hover:border-zinc-400 transition-colors"
            >
              <div className="text-sm font-medium">{link.label}</div>
              <div className="mt-0.5 text-xs text-zinc-500">{t("settings.about.open")}</div>
            </Link>
          ))}
        </div>
        <div className="border-t border-zinc-100 pt-3 text-xs text-zinc-400">
          {t("brand.footer_line")}
        </div>
      </div>
    </div>
  );
}

function SectionContent({ cat }: { cat: string }) {
  switch (cat) {
    case "model": return <ModelSection />;
    case "connections": return <ConnectionsSection />;
    case "advanced": return <AdvancedSection />;
    case "general": return <GeneralSection />;
    case "about": return <AboutSection />;
    default: return <ModelSection />;
  }
}

function SettingsInner() {
  const t = useT();
  const searchParams = useSearchParams();
  const activeCat = searchParams.get("cat") ?? "model";

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-48 shrink-0 border-r border-zinc-200 bg-white overflow-y-auto">
        <div className="px-4 py-3 border-b border-zinc-100">
          <div className="text-xs font-semibold text-zinc-400 tracking-wide uppercase">
            {t("settings.title")}
          </div>
        </div>
        <nav className="p-2 space-y-0.5" aria-label={t("settings.nav_aria")}>
          {CATEGORIES.map((cat) => {
            const isActive = activeCat === cat.id;
            return (
              <Link
                key={cat.id}
                href={`/settings?cat=${cat.id}`}
                aria-current={isActive ? "page" : undefined}
                title={t(cat.descriptionKey)}
                className={`group relative flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors cursor-pointer select-none ${
                  isActive
                    ? "bg-octo-yellow-soft text-zinc-950 font-semibold"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                }`}
              >
                {isActive && (
                  <span
                    className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r"
                    style={{ background: "var(--octo-yellow)" }}
                    aria-hidden
                  />
                )}
                <span
                  className={`inline-flex h-5 w-5 shrink-0 items-center justify-center text-sm leading-none ${
                    isActive ? "pl-1" : ""
                  }`}
                  aria-hidden
                >
                  {cat.emoji}
                </span>
                <span className="truncate">{t(cat.labelKey)}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <section
        key={activeCat}
        className="flex-1 min-w-0 overflow-y-auto bg-zinc-50"
      >
        <div className="mx-auto w-full max-w-4xl px-6 py-6">
          <SectionContent cat={activeCat} />
        </div>
      </section>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<SettingsSuspenseFallback />}>
      <SettingsInner />
    </Suspense>
  );
}
