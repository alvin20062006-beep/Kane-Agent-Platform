/**
 * Locale-aware relative time helper.
 * Supplies a `t` function produced by `useT()` so the caller stays pure.
 * For durations >= 24h we fall back to a locale-appropriate short date
 * (zh → "zh-CN"; everything else → "en-US").
 */
export type TFn = (key: string, fallback?: string) => string;

export function formatRelativeTime(
  iso: string | null | undefined,
  t: TFn,
  locale: "zh" | "en" = "zh"
): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = Date.now();
    const diff = now - d.getTime();
    if (diff < 60_000) return t("time.just_now", "just now");
    if (diff < 3_600_000) {
      const n = Math.floor(diff / 60_000);
      return t("time.minutes_ago", "{n} min ago").replace("{n}", String(n));
    }
    if (diff < 86_400_000) {
      const n = Math.floor(diff / 3_600_000);
      return t("time.hours_ago", "{n}h ago").replace("{n}", String(n));
    }
    return d.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}
