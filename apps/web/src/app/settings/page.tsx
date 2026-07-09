"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";

import { ApiProfilesClient } from "./api-profiles-client";
import { PlatformStatusClient } from "./platform-status-client";
import { SettingsSuspenseFallback } from "./settings-suspense-fallback";

type CategoryId = "platform" | "model" | "connections" | "advanced" | "general" | "about";

type Category = {
  id: CategoryId;
  labelKey: string;
  icon: CategoryId;
  descriptionKey: string;
};

const CATEGORIES: Category[] = [
  {
    id: "platform",
    labelKey: "settings.cat.platform",
    icon: "platform",
    descriptionKey: "settings.cat_desc.platform",
  },
  {
    id: "model",
    labelKey: "settings.cat.model",
    icon: "model",
    descriptionKey: "settings.cat_desc.model",
  },
  {
    id: "connections",
    labelKey: "settings.cat.connections",
    icon: "connections",
    descriptionKey: "settings.cat_desc.connections",
  },
  {
    id: "advanced",
    labelKey: "settings.cat.advanced",
    icon: "advanced",
    descriptionKey: "settings.cat_desc.advanced",
  },
  {
    id: "general",
    labelKey: "settings.cat.general",
    icon: "general",
    descriptionKey: "settings.cat_desc.general",
  },
  {
    id: "about",
    labelKey: "settings.cat.about",
    icon: "about",
    descriptionKey: "settings.cat_desc.about",
  },
];

function SettingsIcon({ name }: { name: CategoryId }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (name === "model") {
    return (
      <svg {...common}>
        <path d="M12 4a4 4 0 0 0-4 4v1H7a3 3 0 0 0 0 6h1v1a4 4 0 0 0 8 0v-1h1a3 3 0 0 0 0-6h-1V8a4 4 0 0 0-4-4Z" />
        <path d="M10 9h4M10 15h4" />
      </svg>
    );
  }
  if (name === "connections") {
    return (
      <svg {...common}>
        <path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1 1" />
        <path d="M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1-1" />
      </svg>
    );
  }
  if (name === "advanced") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" />
      </svg>
    );
  }
  if (name === "general") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
      </svg>
    );
  }
  if (name === "about") {
    return (
      <svg {...common}>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z" />
        <path d="M8 7h8M8 11h6" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12 3 4 7v10l8 4 8-4V7z" />
      <path d="M12 3v18M4 7l8 4 8-4" />
    </svg>
  );
}

function SectionHeading({ title, desc }: { title: string; desc: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--kane-walnut)]">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm text-[var(--kane-muted)]">{desc}</p>
    </div>
  );
}

function PlatformSection() {
  return <PlatformStatusClient />;
}

function ModelSection() {
  const t = useT();
  return (
    <div className="space-y-5">
      <SectionHeading title={t("settings.model.title")} desc={t("settings.model.desc")} />
      <ApiProfilesClient />
    </div>
  );
}

function ConnectionsSection() {
  const t = useT();
  const links = [
    {
      href: "/connections?tab=credentials",
      title: t("settings.connections.credentials.title"),
      desc: t("settings.connections.credentials.desc"),
    },
    {
      href: "/connections?tab=accounts",
      title: t("settings.connections.accounts.title"),
      desc: t("settings.connections.accounts.desc"),
    },
    {
      href: "/connections?tab=adapters",
      title: t("settings.connections.adapters.title"),
      desc: t("settings.connections.adapters.desc"),
    },
  ];
  return (
    <div className="space-y-5">
      <SectionHeading title={t("settings.connections.title")} desc={t("settings.connections.desc")} />
      <div className="grid gap-3 md:grid-cols-3">
        {links.map((item) => (
          <Link key={item.href} href={item.href} className="kane-card p-4 transition hover:border-[var(--kane-amber)]">
            <div className="text-sm font-semibold text-[var(--kane-walnut)]">{item.title}</div>
            <div className="mt-1 text-xs leading-relaxed text-[var(--kane-muted)]">{item.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function AdvancedSection() {
  const t = useT();
  const items = [
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
  ];
  return (
    <div className="space-y-5">
      <SectionHeading title={t("settings.advanced.title")} desc={t("settings.advanced.desc")} />
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((item) => (
          <Link key={item.href} href={item.href} className="kane-card p-4 transition hover:border-[var(--kane-amber)]">
            <div className="text-sm font-semibold text-[var(--kane-walnut)]">{item.label}</div>
            <div className="mt-1 text-xs leading-relaxed text-[var(--kane-muted)]">{item.desc}</div>
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
    <div className="space-y-5">
      <SectionHeading title={t("settings.general.title")} desc={t("settings.general.desc")} />
      <div className="kane-card space-y-3 p-4 text-sm">
        <div>
          <span className="font-semibold text-[var(--kane-walnut)]">{t("settings.general.api_base")}:</span>
          <code className="ml-2 rounded border border-[var(--kane-border)] bg-white/55 px-2 py-0.5 font-mono text-xs">
            {apiBase}
          </code>
        </div>
        <div className="space-y-1.5 text-xs text-[var(--kane-muted)]">
          {[
            ["NEXT_PUBLIC_API_BASE_URL", t("settings.general.env.api_base_url")],
            ["OCTOPUS_LOCAL_BRIDGE_URL", t("settings.general.env.bridge_url")],
            ["OCTOPUS_API_PUBLIC_URL", t("settings.general.env.api_public_url")],
            ["OCTOPUS_BRIDGE_SHARED_SECRET", t("settings.general.env.bridge_secret")],
            ["OCTOPUS_PERSISTENCE / DATABASE_URL", t("settings.general.env.persistence")],
          ].map(([k, v]) => (
            <div key={k}>
              <code>{k}</code> - {v}
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-md border border-amber-200 bg-[var(--kane-amber-soft)] p-4 text-xs text-[var(--kane-amber-deep)]">
        <strong>{t("settings.general.env_title")}</strong>
        {t("settings.general.env_body")}
      </div>
    </div>
  );
}

function AboutSection() {
  const t = useT();
  return (
    <div className="space-y-5">
      <SectionHeading title={t("settings.about.title")} desc={t("settings.about.desc")} />
      <div className="kane-card space-y-3 p-4 text-sm">
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            { label: t("settings.about.link.user_guide"), href: "/help/user-guide" },
            { label: t("settings.about.link.product_notes"), href: "/help/product-notes" },
          ].map((link) => (
            <Link key={link.href} href={link.href} className="rounded-md border border-[var(--kane-border)] bg-white/45 p-3 transition hover:border-[var(--kane-amber)]">
              <div className="text-sm font-semibold text-[var(--kane-walnut)]">{link.label}</div>
              <div className="mt-0.5 text-xs text-[var(--kane-muted)]">{t("settings.about.open")}</div>
            </Link>
          ))}
        </div>
        <div className="border-t border-[var(--kane-border)] pt-3 text-xs text-[var(--kane-muted)]">
          {t("brand.footer_line")}
        </div>
      </div>
    </div>
  );
}

function SectionContent({ cat }: { cat: string }) {
  switch (cat) {
    case "platform":
      return <PlatformSection />;
    case "model":
      return <ModelSection />;
    case "connections":
      return <ConnectionsSection />;
    case "advanced":
      return <AdvancedSection />;
    case "general":
      return <GeneralSection />;
    case "about":
      return <AboutSection />;
    default:
      return <ModelSection />;
  }
}

function SettingsInner() {
  const t = useT();
  const searchParams = useSearchParams();
  const activeCat = searchParams.get("cat") ?? "platform";

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-48 shrink-0 overflow-y-auto border-r border-[var(--kane-border)] bg-[var(--kane-paper-strong)]">
        <div className="border-b border-[var(--kane-border)] px-4 py-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--kane-muted)]">
            {t("settings.title")}
          </div>
        </div>
        <nav className="space-y-0.5 p-2" aria-label={t("settings.nav_aria")}>
          {CATEGORIES.map((cat) => {
            const isActive = activeCat === cat.id;
            return (
              <Link
                key={cat.id}
                href={`/settings?cat=${cat.id}`}
                aria-current={isActive ? "page" : undefined}
                title={t(cat.descriptionKey)}
                className={`group relative flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
                  isActive
                    ? "bg-[var(--kane-amber-soft)] font-semibold text-[var(--kane-walnut)]"
                    : "text-[var(--kane-muted)] hover:bg-white/55 hover:text-[var(--kane-walnut)]"
                }`}
              >
                {isActive ? (
                  <span
                    className="absolute bottom-1.5 left-0 top-1.5 w-0.5 rounded-r"
                    style={{ background: "var(--kane-amber)" }}
                    aria-hidden
                  />
                ) : null}
                <span className={isActive ? "text-[var(--kane-amber-deep)]" : "text-[var(--kane-moss)]"}>
                  <SettingsIcon name={cat.icon} />
                </span>
                <span className="truncate">{t(cat.labelKey)}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <section key={activeCat} className="min-w-0 flex-1 overflow-y-auto bg-[var(--kane-page)]">
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
