export function buildCallbackExample(
  apiBase: string,
  taskId?: string | null,
  runId?: string | null,
): string {
  const base = apiBase.replace(/\/$/, "");
  const tid = taskId?.trim() || "task_xxx";
  const rid = runId?.trim() || "run_xxx";
  return [
    `POST ${base}/integrations/bridge/complete`,
    "{",
    `  "task_id": "${tid}",`,
    `  "run_id": "${rid}",`,
    '  "status": "succeeded",',
    '  "output": "your result summary",',
    '  "integration_path": "manual_agent"',
    "}",
  ].join("\n");
}
