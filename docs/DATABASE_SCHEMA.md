# DATABASE_SCHEMA（存储模型）

## 运行模式

`apps/api` 支持两种持久化后端（由环境变量选择，详见 `apps/api/app/settings_env.py`）：

| 模式 | 环境变量 | 说明 |
|------|-----------|------|
| **文件（默认）** | `OCTOPUS_PERSISTENCE=file`（或未设置） | 多个 JSON 文件承载实体列表，路径由 `OCTOPUS_API_DATA_DIR` 或默认 `apps/api/data` 决定 |
| **PostgreSQL** | `OCTOPUS_PERSISTENCE=postgres` + `DATABASE_URL` | 使用 `octopus_entities` 表：`entity_type`、`entity_id`、`data`（JSONB）；由 `DbStore` 实现与文件仓库相同的仓储接口 |

Alembic 迁移见 `apps/api`；启用 Postgres 前需执行迁移至最新。

## 概念实体（逻辑模型）

无论文件还是 JSONB 行存，产品侧仍区分以下实体类型（与代码中 `entity_type` / 仓库一致，包括但不限于）：

- `agents`、`tasks`、`task_events`、`runs`、`run_logs`、`task_assignments`
- `conversations`、`conversation_messages`
- `skills`、`accounts`、`credentials`、`memory`、`memory_candidates`
- `execution_policies`、`notifications`、`reports`
- `local_bridge` 相关登记状态 等

具体字段以 Pydantic 模型与 `packages/schemas` 为准；OpenAPI 反映当前 API 负载形状。

## 与「理想关系型拆表」的差异

当前 Postgres 路径为 **JSONB 实体表兼容层**，便于从文件存储平滑迁移；**未**要求已实现 PRD 中每一张独立范式的表。若未来拆表，应新增迁移与文档更新。

## 记忆与向量

记忆审批、候选条目等已在当前 API 中持久化；**全文/向量检索**若未在部署中配置，则表现为本地 JSON/DB 查询能力，而非托管向量服务。

## 延伸阅读

- `docs/API.md` — 对外 REST 与 `/health` 中的 `persistence` 字段
