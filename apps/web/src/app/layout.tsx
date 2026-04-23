import type { Metadata } from "next";

import { SidebarNav } from "@/components/sidebar-nav";
import { TopBar } from "@/components/top-bar";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kāne · AI Agent Platform",
  description:
    "Kāne & Kanaloa — an AI agent platform with persisted task lifecycle, bridge workflow, and monitoring.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full bg-zinc-50 text-zinc-950">
        <LocaleProvider>
          <div className="flex h-full min-h-screen">
            <aside className="w-56 shrink-0 border-r border-[var(--octo-blue-deep)] bg-white">
              <SidebarNav />
            </aside>
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main className="flex-1 min-h-0 overflow-y-auto">{children}</main>
            </div>
          </div>
        </LocaleProvider>
      </body>
    </html>
  );
}
