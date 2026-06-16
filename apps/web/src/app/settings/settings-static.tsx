"use client";

import { useT } from "@/lib/i18n/LocaleProvider";

import { ApiProfilesClient } from "./api-profiles-client";

type Props = {
  apiBase: string;
};

/** Always rendered so API Profiles / base URL are visible even when other GETs fail. */
export function SettingsStaticSections({ apiBase }: Props) {
  const t = useT();
  return (
    <>
      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
        <div className="text-sm font-semibold">{t("settings.static.browser_api")}</div>
        <div className="text-sm text-zinc-700">
          {t("settings.static.api_base_intro")}
          <code className="rounded border border-zinc-200 bg-zinc-50 px-1 text-xs">
            NEXT_PUBLIC_API_BASE_URL
          </code>
          {t("settings.static.api_base_intro_suffix")}
          <span className="ml-2 rounded border border-zinc-200 bg-zinc-50 px-2 py-1 font-mono text-xs">
            {apiBase}
          </span>
        </div>
        <p className="text-xs text-zinc-500">{t("settings.static.partial_404_hint")}</p>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("settings.static.env_heading")}</div>
        <div className="mt-3 space-y-2 text-sm text-zinc-700">
          <div>
            <code className="text-xs">NEXT_PUBLIC_API_BASE_URL</code> —{" "}
            {t("settings.general.env.api_base_url_desc")}
          </div>
          <div>
            <code className="text-xs">OCTOPUS_LOCAL_BRIDGE_URL</code> —{" "}
            {t("settings.general.env.bridge_url_desc")}
          </div>
          <div>
            <code className="text-xs">OCTOPUS_API_PUBLIC_URL</code> —{" "}
            {t("settings.general.env.api_public_url_desc")}
          </div>
          <div>
            <code className="text-xs">OCTOPUS_BRIDGE_SHARED_SECRET</code> —{" "}
            {t("settings.general.env.bridge_secret_desc")}
          </div>
          <div>
            <code className="text-xs">OCTOPUS_PERSISTENCE</code> /{" "}
            <code className="text-xs">DATABASE_URL</code> — {t("settings.general.env.persistence_desc")}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="text-sm font-semibold">{t("settings.static.profiles_heading")}</div>
        <p className="mt-1 text-xs text-zinc-500">{t("settings.static.profiles_data_hint")}</p>
        <div className="mt-4">
          <ApiProfilesClient />
        </div>
      </section>
    </>
  );
}
