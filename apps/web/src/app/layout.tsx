import type { Metadata } from "next";

import { SidebarNav } from "@/components/sidebar-nav";
import { TopBar } from "@/components/top-bar";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kane - AI Agent Platform",
  description: "Kane Agent Platform v2.0.0 local-first AI agent control plane.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full overflow-hidden bg-[var(--kane-walnut-ink)] p-[10px] text-[var(--foreground)]">
        <LocaleProvider>
          <div className="kane-app-frame kane-shell-bg flex h-[calc(100vh-20px)] min-h-0 overflow-hidden rounded-[28px]">
            <aside className="kane-sidebar-panel relative z-10 w-56 shrink-0 overflow-hidden rounded-[26px] border-r border-[var(--kane-border-strong)] bg-[var(--kane-sidebar)]">
              <SidebarNav />
            </aside>
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main className="min-h-0 flex-1 overflow-y-auto bg-[var(--kane-page)]">{children}</main>
            </div>
          </div>
        </LocaleProvider>
      </body>
    </html>
  );
}
