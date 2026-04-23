"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useLocale, useT } from "@/lib/i18n/LocaleProvider";

const DOCS: Record<string, { titleKey: string; source: string }> = {
  "user-guide": {
    titleKey: "help.doc.user_guide.title",
    source: "USER_GUIDE_LOCAL_AGENTS.md",
  },
  "beta-limitations": {
    titleKey: "help.doc.beta_limits.title",
    source: "docs/BETA_LIMITATIONS.md",
  },
  roadmap: {
    titleKey: "help.doc.roadmap.title",
    source: "docs/ROADMAP_UX_AND_THREAD.md",
  },
  prd: {
    titleKey: "help.doc.prd.title",
    source: "docs/PRD.md",
  },
};

// Small safe markdown renderer (no raw HTML injection).
function renderMarkdown(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let inCode = false;
  let inTable = false;
  let listType: "ul" | "ol" | null = null;

  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const inline = (s: string) => {
    let x = esc(s);
    x = x.replace(
      /`([^`]+)`/g,
      '<code class="rounded bg-zinc-100 px-1 py-0.5 text-[0.85em]">$1</code>'
    );
    x = x.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    x = x.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    x = x.replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a class="text-[color:var(--octo-blue-deep)] underline underline-offset-2" href="$2">$1</a>'
    );
    return x;
  };

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };
  const closeTable = () => {
    if (inTable) {
      out.push("</tbody></table></div>");
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("```")) {
      closeList();
      closeTable();
      if (!inCode) {
        out.push(
          '<pre class="my-4 overflow-auto rounded-lg bg-zinc-950 p-4 text-xs text-zinc-100"><code>'
        );
        inCode = true;
      } else {
        out.push("</code></pre>");
        inCode = false;
      }
      continue;
    }
    if (inCode) {
      out.push(esc(line));
      continue;
    }

    if (/^\s*\|/.test(line) && line.includes("|")) {
      const cells = line
        .trim()
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((c) => c.trim());
      const next = lines[i + 1] ?? "";
      const isHeaderSep = /^\s*\|?\s*:?-{2,}/.test(next);
      if (!inTable) {
        if (isHeaderSep) {
          closeList();
          out.push(
            '<div class="my-4 overflow-x-auto rounded-lg border border-zinc-200"><table class="w-full text-sm"><thead class="bg-zinc-50"><tr>'
          );
          for (const c of cells)
            out.push(
              `<th class="border-b border-zinc-200 px-3 py-2 text-left font-medium">${inline(c)}</th>`
            );
          out.push("</tr></thead><tbody>");
          inTable = true;
          i++;
          continue;
        }
      } else {
        if (isHeaderSep) continue;
        out.push("<tr>");
        for (const c of cells)
          out.push(
            `<td class="border-t border-zinc-100 px-3 py-2 align-top">${inline(c)}</td>`
          );
        out.push("</tr>");
        continue;
      }
    } else if (inTable) {
      closeTable();
    }

    const hm = /^(#{1,6})\s+(.+)$/.exec(line);
    if (hm) {
      closeList();
      const level = hm[1].length;
      const sizes = [
        "text-3xl font-bold",
        "text-2xl font-bold",
        "text-xl font-semibold",
        "text-lg font-semibold",
        "text-base font-semibold",
        "text-sm font-semibold",
      ];
      out.push(
        `<h${level} class="mt-6 mb-3 ${sizes[level - 1]}">${inline(hm[2])}</h${level}>`
      );
      continue;
    }

    if (/^-{3,}$|^={3,}$/.test(line.trim())) {
      closeList();
      out.push('<hr class="my-6 border-zinc-200" />');
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      if (listType !== "ul") {
        closeList();
        out.push('<ul class="my-3 list-disc pl-6 space-y-1">');
        listType = "ul";
      }
      out.push(`<li>${inline(line.replace(/^\s*[-*+]\s+/, ""))}</li>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (listType !== "ol") {
        closeList();
        out.push('<ol class="my-3 list-decimal pl-6 space-y-1">');
        listType = "ol";
      }
      out.push(`<li>${inline(line.replace(/^\s*\d+\.\s+/, ""))}</li>`);
      continue;
    }

    if (!line.trim()) {
      closeList();
      continue;
    }

    closeList();
    out.push(`<p class="my-2 leading-relaxed">${inline(line)}</p>`);
  }

  closeList();
  closeTable();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

/**
 * Given the default doc source (zh) and the current locale, return the
 * locale-specific source path. Strips `.md` and inserts `.en` before it.
 */
function localizedSource(source: string, locale: "zh" | "en"): string {
  if (locale === "zh") return source;
  return source.replace(/\.md$/i, ".en.md");
}

export function HelpDocClient({ doc }: { doc: string }) {
  const t = useT();
  const { locale } = useLocale();
  const meta = DOCS[doc];

  const [content, setContent] = useState<string>("");
  const [resolvedSource, setResolvedSource] = useState<string>("");

  useEffect(() => {
    if (!meta) return;
    let cancelled = false;

    const fetchMd = async () => {
      const primary = localizedSource(meta.source, locale);
      const fallback = meta.source;
      const tryFetch = async (p: string) => {
        const res = await fetch(`/${p}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.text();
      };

      try {
        const md = await tryFetch(primary);
        if (cancelled) return;
        setContent(md);
        setResolvedSource(primary);
      } catch {
        try {
          const md = await tryFetch(fallback);
          if (cancelled) return;
          setContent(md);
          setResolvedSource(fallback);
        } catch {
          if (cancelled) return;
          setContent(
            `# ${t("help.doc.load_failed_heading")}\n\n${t("help.doc.load_failed_body").replace(
              "{source}",
              fallback
            )}`
          );
          setResolvedSource(fallback);
        }
      }
    };

    fetchMd();
    return () => {
      cancelled = true;
    };
  }, [meta, locale, t]);

  if (!meta) {
    return (
      <div className="mx-auto max-w-4xl p-6 text-sm text-zinc-500">
        {t("help.doc.load_failed_heading")}
      </div>
    );
  }

  const html = renderMarkdown(content);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <Link
          href="/settings?cat=about"
          className="text-xs text-zinc-500 hover:text-zinc-800"
        >
          {t("help.doc.back_to_settings")}
        </Link>
        <div className="text-xs text-zinc-400">
          {t("help.doc.source_label")}:{" "}
          <code className="font-mono">{resolvedSource || meta.source}</code>
        </div>
      </div>
      <article
        className="rounded-xl border border-zinc-200 bg-white px-7 py-8 text-sm text-zinc-800"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
