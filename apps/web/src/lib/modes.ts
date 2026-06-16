/**
 * 三档执行模式的 UI 文案中心。
 *
 * 设计要点：
 * - `commander` / `pilot` / `direct_agent` 是后端真实取值（见 Task.execution_mode）。
 * - 在对话/操控舱/升级任务三处统一读取本模块，避免重复的中文硬编码。
 * - `direct_agent` 根据当前 operator 显示不同 label：
 *     · Kanaloa（内置）: "内置直连"
 *     · 其他 Agent    : "外部直连"
 *
 * i18n：label 通过 t(key) 取，所以这里只返回 key。
 */

export type ExecutionMode = "commander" | "pilot" | "direct_agent";

export type ModeItem = {
  id: ExecutionMode;
  /** t() 用 key，调用方自己翻译 */
  labelKey: string;
  /** 是否仅 Kanaloa 可用（外部 Agent 会被自动禁用并降级到 direct_agent） */
  kanaloaOnly: boolean;
};

export function listModesFor(isKanaloa: boolean): ModeItem[] {
  if (!isKanaloa) {
    return [
      {
        id: "direct_agent",
        labelKey: "mode.direct_external",
        kanaloaOnly: false,
      },
    ];
  }
  return [
    { id: "direct_agent", labelKey: "mode.direct_builtin", kanaloaOnly: false },
    { id: "commander", labelKey: "mode.commander", kanaloaOnly: true },
    { id: "pilot", labelKey: "mode.pilot", kanaloaOnly: true },
  ];
}

/** 供非 Kanaloa 时自动纠正 */
export function coerceModeForOperator(
  mode: ExecutionMode,
  isKanaloa: boolean
): ExecutionMode {
  if (!isKanaloa) return "direct_agent";
  return mode;
}

export function modeLabelKey(mode: ExecutionMode, isKanaloa: boolean): string {
  if (mode === "commander") return "mode.commander";
  if (mode === "pilot") return "mode.pilot";
  return isKanaloa ? "mode.direct_builtin" : "mode.direct_external";
}
