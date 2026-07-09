"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useT } from "@/lib/i18n/LocaleProvider";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type IconName =
  | "cockpit"
  | "conversations"
  | "tasks"
  | "agents"
  | "skills"
  | "orchestrator"
  | "dashboard"
  | "settings";

type NavItem = { labelKey: string; href: string; icon: IconName };

const MAIN_NAV: NavItem[] = [
  { labelKey: "nav.cockpit", href: "/cockpit", icon: "cockpit" },
  { labelKey: "nav.conversations", href: "/conversations", icon: "conversations" },
  { labelKey: "nav.tasks", href: "/tasks", icon: "tasks" },
  { labelKey: "nav.agents", href: "/agent-fleet", icon: "agents" },
  { labelKey: "nav.skills", href: "/skills", icon: "skills" },
  { labelKey: "nav.orchestrator", href: "/orchestrator", icon: "orchestrator" },
  { labelKey: "nav.dashboard", href: "/dashboard", icon: "dashboard" },
  { labelKey: "nav.settings", href: "/settings", icon: "settings" },
];

function NavIcon({ name }: { name: IconName }) {
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

  if (name === "conversations") {
    return (
      <svg {...common}>
        <path d="M21 12a7.5 7.5 0 0 1-7.5 7.5H8l-5 2 1.7-4A7.5 7.5 0 1 1 21 12Z" />
      </svg>
    );
  }
  if (name === "tasks") {
    return (
      <svg {...common}>
        <path d="M9 5h6" />
        <path d="M9 3h6v4H9z" />
        <path d="M5 7h14v13H5z" />
        <path d="m8 13 2 2 4-5" />
      </svg>
    );
  }
  if (name === "agents") {
    return (
      <svg {...common}>
        <circle cx="12" cy="7" r="3" />
        <path d="M5 21a7 7 0 0 1 14 0" />
        <path d="M4 10h3M17 10h3" />
      </svg>
    );
  }
  if (name === "skills") {
    return (
      <svg {...common}>
        <path d="M12 3v4M12 17v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M3 12h4M17 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
      </svg>
    );
  }
  if (name === "orchestrator") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3" />
        <circle cx="5" cy="6" r="2" />
        <circle cx="19" cy="6" r="2" />
        <circle cx="12" cy="20" r="2" />
        <path d="M7 7.5 10 10M17 7.5 14 10M12 15v3" />
      </svg>
    );
  }
  if (name === "dashboard") {
    return (
      <svg {...common}>
        <path d="M4 13h6V4H4zM14 20h6V4h-6zM4 20h6v-3H4z" />
      </svg>
    );
  }
  if (name === "settings") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2.8v2.1" />
        <path d="M12 19.1v2.1" />
        <path d="M4.3 6.1 5.8 7.6" />
        <path d="m18.2 16.4 1.5 1.5" />
        <path d="M2.8 12h2.1" />
        <path d="M19.1 12h2.1" />
        <path d="m4.3 17.9 1.5-1.5" />
        <path d="m18.2 7.6 1.5-1.5" />
        <path d="M8.2 4.4 9 6.3" />
        <path d="m15 17.7.8 1.9" />
        <path d="m4.4 15.8 1.9-.8" />
        <path d="m17.7 9 1.9-.8" />
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

function NavLink({
  item,
  active,
  label,
}: {
  item: NavItem;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      title={label}
      className={cx(
        "group relative flex items-center gap-2 rounded-md px-2.5 py-2 text-[15px] transition-colors",
        active
          ? "bg-[var(--kane-amber-soft)] font-semibold text-[var(--kane-walnut)] shadow-[inset_0_0_0_1px_rgba(232,118,19,0.13)]"
          : "text-[var(--foreground)] hover:bg-white/45 hover:text-[var(--kane-walnut)]"
      )}
    >
      {active ? (
        <span
          className="absolute bottom-1.5 left-0 top-1.5 w-0.5 rounded-r"
          style={{ background: "var(--kane-amber)" }}
          aria-hidden
        />
      ) : null}
      <span
        className={cx(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center",
          active ? "text-[var(--kane-amber-deep)]" : "text-[var(--kane-moss)]"
        )}
        aria-hidden
      >
        <NavIcon name={item.icon} />
      </span>
      <span className="truncate">{label}</span>
    </Link>
  );
}

export function SidebarNav() {
  const pathname = usePathname();
  const t = useT();

  const isActive = (href: string) => {
    const path = href.split("?")[0];
    return pathname === path || pathname.startsWith(path + "/");
  };

  return (
    <div className="flex h-full flex-col bg-[var(--kane-sidebar)]">
      <div className="flex h-[86px] items-center gap-2 border-b border-[var(--kane-border-strong)] bg-[linear-gradient(180deg,#fff8ee,#ffefd5)] px-3">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-base font-bold"
          style={{
            background: "linear-gradient(180deg, #ffe1b8, #ffd092)",
            color: "var(--kane-amber-deep)",
          }}
          aria-hidden
        >
          🐙
        </span>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-semibold leading-tight text-[var(--kane-walnut)]">Kane</div>
          <div className="truncate text-[10px] leading-tight text-[var(--kane-muted)]">{t("brand.subtitle")}</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2" aria-label={t("nav.settings")}>
        <ul className="space-y-0.5">
          {MAIN_NAV.map((item) => (
            <li key={item.href}>
              <NavLink item={item} active={isActive(item.href)} label={t(item.labelKey)} />
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-1 border-t border-[var(--kane-border)] bg-white/35 px-3 py-2">
        <div className="text-[10px] font-medium uppercase text-[var(--kane-muted)]">
          {t("nav.more")}
        </div>
        <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[10px]">
          <Link href="/observer" className="text-[var(--kane-muted)] underline hover:text-[var(--kane-walnut)]">
            {t("nav.observer")}
          </Link>
          <Link href="/memory" className="text-[var(--kane-muted)] underline hover:text-[var(--kane-walnut)]">
            {t("nav.memory")}
          </Link>
        </div>
        <div className="flex items-center gap-1.5 pt-1 text-[10px] text-[var(--kane-muted)]">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--kane-moss)" }}
            aria-hidden
          />
          {t("common.version")}
        </div>
      </div>
    </div>
  );
}
