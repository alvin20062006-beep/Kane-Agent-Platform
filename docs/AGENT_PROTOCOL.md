# AGENT_PROTOCOL（草案 / Phase 0 冻结接口形状）

本阶段只做协议冻结与 mock 展示，不实现外部 Agent 的真实接入与调度。

## Agent 能力声明（目标）

每个 Agent 至少声明：

- `agent_id`
- `display_name`
- `type`（builtin/external）
- `status`（idle/running/stalled/offline/degraded）
- `capabilities`
  - `can_chat`
  - `can_code`
  - `can_browse`
  - `can_use_skills`
  - `can_generate_images`
  - `can_run_local_commands`
  - `can_stream`
  - `supports_structured_task`
  - `supports_mobile_input`
- `last_heartbeat_at`（占位）

## TODO（phase>=3）

- TODO(phase>=3): Agent Adapter（OpenClaw / Claude Code）接入
- TODO(phase>=3): 任务投递、结果回传、心跳上报协议落地
- TODO(phase>=3): Watchdog 规则：离线/卡住/降级判定与自动处理策略

