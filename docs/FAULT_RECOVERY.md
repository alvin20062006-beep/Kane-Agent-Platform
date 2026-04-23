# FAULT_RECOVERY（故障恢复 Beta）

## 用户可执行

- **Retry**：`POST /tasks/{id}/retry`（自 `failed` 或 `waiting_approval` 等允许状态）
- **Mark failed**：`POST /tasks/{id}/fail`（运维/演示强制失败）
- **外部 handoff 卡住**：检查 `apps/local-bridge/data/handoffs/` 与任务 Timeline；补交 `/integrations/bridge/complete`

## Watchdog（Beta 规则）

- `running` 且 `updated_at` 超过 **15 分钟** → 记为 stalled_tasks（提示级）
- Bridge `/health` 失败 → `bridge_unreachable` 事件

## 运营建议

- 保留 `apps/api/data` 目录备份（Beta 文件库）
- 失败 Run 在 `/metrics` 中计数；结合 Timeline 定位
