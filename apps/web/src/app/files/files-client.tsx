"use client";

import { useMemo, useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import { apiDelete, apiPost } from "@/lib/api";

export type FileArtifact = {
  file_id: string;
  name: string;
  path?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  source: "task" | "agent" | "user" | "bridge";
  source_id?: string | null;
  task_id?: string | null;
  conversation_id?: string | null;
  agent_id?: string | null;
  description?: string | null;
  tags?: string[];
  created_at: string;
};

function fmtBytes(n: number | null | undefined) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

const SOURCES: Array<FileArtifact["source"] | "all"> = [
  "all",
  "user",
  "task",
  "agent",
  "bridge",
];

export function FilesClient({ initialFiles }: { initialFiles: FileArtifact[] }) {
  const t = useT();
  const [files, setFiles] = useState<FileArtifact[]>(initialFiles);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<FileArtifact["source"] | "all">("all");
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [description, setDescription] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return files.filter((f) => {
      if (filter !== "all" && f.source !== filter) return false;
      if (!needle) return true;
      return (
        f.name.toLowerCase().includes(needle) ||
        (f.path ?? "").toLowerCase().includes(needle) ||
        (f.description ?? "").toLowerCase().includes(needle) ||
        (f.task_id ?? "").toLowerCase().includes(needle)
      );
    });
  }, [files, filter, q]);

  const registerFile = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const resp = await apiPost<{ data: FileArtifact }>("/files", {
        name: name.trim(),
        path: path.trim() || null,
        description: description.trim() || null,
        source: "user",
      });
      setFiles((prev) => [resp.data, ...prev]);
      setName("");
      setPath("");
      setDescription("");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm(t("action.confirm_delete"))) return;
    setBusy(true);
    try {
      await apiDelete(`/files/${encodeURIComponent(id)}`);
      setFiles((prev) => prev.filter((f) => f.file_id !== id));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-zinc-200 bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">{t("files.register.title")}</div>
            <div className="text-xs text-zinc-500">{t("files.register.hint")}</div>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          <input
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm"
            placeholder={t("files.col.name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm"
            placeholder={t("files.field.path")}
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <input
            className="rounded-md border border-zinc-200 px-3 py-2 text-sm"
            placeholder={t("files.field.description")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div>
          <button
            type="button"
            disabled={busy || !name.trim()}
            onClick={registerFile}
            className="rounded-md px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
            style={{ backgroundColor: "var(--octo-royal-blue)" }}
          >
            {t("action.save")}
          </button>
        </div>
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 px-4 py-3">
          <div className="flex gap-1">
            {SOURCES.map((s) => {
              const active = filter === s;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => setFilter(s)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    active
                      ? "bg-zinc-900 text-white"
                      : "border border-zinc-200 text-zinc-600 hover:bg-zinc-50"
                  }`}
                >
                  {t(`files.source.${s}`)}
                </button>
              );
            })}
          </div>
          <div className="flex-1" />
          <input
            className="w-full max-w-[240px] rounded-md border border-zinc-200 px-3 py-1.5 text-xs"
            placeholder={t("files.search_placeholder")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        {filtered.length === 0 ? (
          <div className="p-6 text-sm text-zinc-500">{t("files.empty")}</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-zinc-600">
              <tr>
                <th className="px-4 py-3 text-left font-medium">{t("files.col.name")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("files.col.source")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("files.col.task")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("files.col.created")}</th>
                <th className="px-4 py-3 text-left font-medium">{t("files.col.size")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((f) => (
                <tr key={f.file_id} className="border-t border-zinc-200 align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium">{f.name}</div>
                    {f.path && (
                      <div className="text-xs text-zinc-500 truncate max-w-[280px]" title={f.path}>
                        {f.path}
                      </div>
                    )}
                    {f.description && (
                      <div className="mt-1 text-xs text-zinc-600">{f.description}</div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full border border-zinc-200 px-2 py-0.5 text-xs">
                      {t(`files.source.${f.source}`)}
                    </span>
                    {f.agent_id && (
                      <div className="mt-1 text-xs text-zinc-500 font-mono">{f.agent_id}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-zinc-700">
                    {f.task_id ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-700">{f.created_at}</td>
                  <td className="px-4 py-3 text-xs text-zinc-700">{fmtBytes(f.size_bytes)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      className="text-xs text-red-600 hover:underline"
                      onClick={() => remove(f.file_id)}
                    >
                      {t("action.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
