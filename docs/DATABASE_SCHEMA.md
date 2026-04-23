# DATABASE_SCHEMA（文档阶段）

本阶段 **不落地生产数据库**。这里冻结核心表的字段草案，用于后续 Phase 2+ 实现。

> 注意：以下为“目标模型文档”，当前 `apps/api` 仅返回 mock 数据，不会写入任何 DB。

## 核心表（摘要）

- `users`
- `agents`
- `agent_adapters`
- `accounts`
- `credentials`
- `skills`
- `skill_versions`
- `tasks`
- `task_events`
- `runs`
- `run_logs`
- `execution_policies`
- `notifications`
- `watchdog_events`
- `memories`
- `memory_candidates`
- `memory_links`
- `memory_access_rules`
- `projects`
- `local_bridges`
- `browser_sessions`
- `comparison_reports`
- `audit_logs`

## 记忆系统（重点）

### `memories`

- `memory_id` (uuid)
- `user_id` (uuid)
- `project_id` (uuid, nullable)
- `memory_type` (enum)
- `title` (text)
- `content` (text)
- `structured_payload` (jsonb)
- `source_type` (enum)
- `source_id` (text/uuid)
- `confidence` (float)
- `status` (enum)
- `visibility` (enum)
- `created_at` / `updated_at`
- `expires_at` (timestamp, nullable)

`memory_type` 示例：
`user_preference | project_state | agent_performance | skill_stability | failure_pattern | workflow_pattern | risk_note | account_state | policy_preference`

### `memory_candidates`

- `candidate_id`
- `source_run_id`
- `proposed_by` (agent_id / system)
- `memory_type`
- `content`
- `reason`
- `confidence`
- `status` (`pending | approved | rejected | auto_expired`)
- `created_at` / `reviewed_at`

### `memory_access_rules`

- `rule_id`
- `memory_scope`
- `allowed_agent_ids` (array)
- `allowed_skill_ids` (array)
- `visibility`
- `created_at`

## TODO（phase>=2）

- TODO(phase>=2): 选择落地方案（PostgreSQL + Alembic + SQLModel/SQLAlchemy）
- TODO(phase>=2): 引入 pgvector 或外部向量库（Qdrant）用于检索
- TODO(phase>=2): 记忆治理（审批/过期/删除/权限）与审计日志

