# @octopus/schemas（Phase 1 foundation）

本包用于前后端共享“字段命名与协议形状”。当前阶段：

- **只提供 JSON Schema 文件**
- 不要求代码生成
- 不保证完整性（会随 Phase 2+ 演进）

## 目录

- `json/`: JSON Schema（草案）

## 约定

- 所有 mock API 响应都应包含 `is_mock: true`（或在顶层 payload 标记）
- 所有资源应包含稳定主键字段（如 `agent_id`、`task_id` 等）

