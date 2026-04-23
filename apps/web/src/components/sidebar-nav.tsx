"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useT } from "@/lib/i18n/LocaleProvider";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type NavItem = { labelKey: string; href: string; icon: string };

const MAIN_NAV: NavItem[] = [
  { labelKey: "nav.conversations", href: "/conversations", icon: "💬" },
  { labelKey: "nav.cockpit", href: "/cockpit", icon: "🎛" },
  { labelKey: "nav.tasks", href: "/tasks", icon: "📝" },
  { labelKey: "nav.agents", href: "/agent-fleet", icon: "🤖" },
  { labelKey: "nav.skills", href: "/skills", icon: "🔧" },
  { labelKey: "nav.memory", href: "/memory", icon: "🧩" },
  { labelKey: "files.title", href: "/files", icon: "🗂️" },
  { labelKey: "nav.dashboard", href: "/dashboard", icon: "💻" },
  { labelKey: "nav.settings", href: "/settings", icon: "⚙" },
];

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
          ? "bg-[var(--octo-yellow-soft)] text-zinc-950 font-semibold"
          : "text-zinc-800 hover:bg-zinc-100 hover:text-zinc-900"
      )}
    >
      {active && (
        <span
          className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-r"
          style={{ background: "var(--octo-yellow)" }}
          aria-hidden
        />
      )}
      <span
        className={cx(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center text-sm leading-none",
          active ? "pl-1" : ""
        )}
        aria-hidden
      >
        {item.icon}
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
    <div className="flex h-full flex-col bg-white">
      {/* 品牌区：极简，仅图标 + 小标 Kāne */}
      <div className="flex h-12 items-center gap-2 border-b border-[var(--octo-blue-deep)] bg-[var(--octo-blue)] px-3">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-md text-base shrink-0"
          style={{
            background: "var(--octo-yellow)",
            color: "var(--octo-blue-deep)",
          }}
          aria-hidden
        >
          🐙
        </span>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-semibold tracking-wide text-white">Kāne</div>
          <div className="truncate text-[10px] text-blue-100">{t("brand.subtitle")}</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2" aria-label={t("nav.settings")}>
        <ul className="space-y-0.5">
          {MAIN_NAV.map((item) => (
            <li key={item.href}>
              <NavLink
                item={item}
                active={isActive(item.href)}
                label={t(item.labelKey)}
              />
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-black/10 px-3 py-2">
        <div className="flex items-center gap-1.5 text-[10px] text-zinc-700">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--octo-royal-blue)" }}
            aria-hidden
          />
          {t("common.beta")}
        </div>
      </div>
    </div>
  );
}
