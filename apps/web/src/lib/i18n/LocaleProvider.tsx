"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { DICTIONARIES, type Locale } from "./dict";

const STORAGE_KEY = "kane.locale";
const DEFAULT_LOCALE: Locale = "zh";

type LocaleCtx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, fallback?: string) => string;
};

const LocaleContext = createContext<LocaleCtx | null>(null);

/** 从 localStorage 读取，无则回退到 DEFAULT_LOCALE */
function readInitialLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "zh" || v === "en") return v;
  } catch {
    /* ignore (SSR / private mode) */
  }
  return DEFAULT_LOCALE;
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // 首次 SSR 时使用 DEFAULT，挂载后再 sync，避免 hydration 失配
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setLocaleState(readInitialLocale());
    setReady(true);
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
      document.documentElement.lang = l === "zh" ? "zh-CN" : "en";
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    } catch {
      /* ignore */
    }
  }, [locale, ready]);

  const t = useCallback(
    (key: string, fallback?: string) => {
      const dict = DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
      return dict[key] ?? fallback ?? key;
    },
    [locale]
  );

  const value = useMemo<LocaleCtx>(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleCtx {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    // 开发容错：未包在 Provider 时返回默认实现，避免渲染崩溃
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => {
        /* noop */
      },
      t: (k, fb) => DICTIONARIES[DEFAULT_LOCALE][k] ?? fb ?? k,
    };
  }
  return ctx;
}

/** 直接获取 t 函数 */
export function useT() {
  return useLocale().t;
}
