"use client";

import { getApiBaseUrl } from "@/lib/api";
import { buildCallbackExample } from "@/lib/bridge-callback";
import { useT } from "@/lib/i18n/LocaleProvider";

type Props = {
  handoffDir?: string | null;
  apiBase?: string | null;
  taskId?: string | null;
  runId?: string | null;
  testId?: string;
};

export function HandoffCallbackBlock({
  handoffDir,
  apiBase,
  taskId,
  runId,
  testId = "handoff-callback-block",
}: Props) {
  const t = useT();
  const base = apiBase?.trim() || getApiBaseUrl();

  return (
    <div
      data-testid={testId}
      className="space-y-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-xs text-sky-950"
    >
      <div>
        <div className="text-zinc-500">{t("bridge.runtime.handoff_dir")}</div>
        <div className="mt-1 font-mono break-all">
          {handoffDir?.trim() || t("dashboard.none")}
        </div>
      </div>
      <div>
        <div className="text-zinc-500">{t("bridge.runtime.callback_example")}</div>
        <pre className="mt-1 overflow-x-auto rounded border border-sky-100 bg-white p-2 text-[11px] leading-relaxed">
          {buildCallbackExample(base, taskId, runId)}
        </pre>
      </div>
    </div>
  );
}
