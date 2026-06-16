import type { CompletionMode } from "./task-completion";

export const COMPLETION_MODE_TITLE_KEYS: Record<CompletionMode, string> = {
  builtin_auto: "completion.builtin.title",
  bridge_sync: "completion.bridge.title",
  handoff_callback: "completion.handoff.title",
  policy_approve: "completion.approve.title",
  pilot_steps: "completion.pilot.title",
  unknown: "completion.unknown.title",
};
