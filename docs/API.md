# API（HTTP 概览）

Kane / Kāne 控制面 **FastAPI** 服务，默认定位为 **本地私有部署 / Owner 自用**，不是开箱即用的公网多租户 SaaS。默认数据落在 **文件 JSON**（`OCTOPUS_PERSISTENCE=file`，运行时目录 `apps/data/` 勿提交）；可选 **PostgreSQL**（`OCTOPUS_PERSISTENCE=postgres` + `DATABASE_URL`），实体以 JSONB 行存储（见 `docs/DATABASE_SCHEMA.md`）。**Docker Compose** 下 Local Bridge 回调 API 请使用 `OCTOPUS_API_PUBLIC_URL=http://api:8000`（容器网络）；本机直连可用 `http://127.0.0.1:8000`。

- **Base URL（本地）**：`http://127.0.0.1:8000`
- **OpenAPI / Swagger UI**：`http://127.0.0.1:8000/docs`
- **旧版列表前缀**：部分资源同时暴露在 `/v1/agents`、`/v1/tasks` 等，与无前缀路径共用同一持久化层（优先使用无 `/v1` 路径做新集成）。

### LLM（章鱼内置 Agent）

- **API Key（优先级）**：`OCTOPUS_LLM_API_KEY` → `LLM_API_KEY` → Profile 中的 `api_key`（仅本地兼容；**不推荐**将真实 Key 写入 `apps/data` 下 JSON）。
- **输出 token 上限**：`LLM_MAX_TOKENS` / `OCTOPUS_LLM_MAX_TOKENS` 未设置、`unlimited`、`infinite`、`auto`、`none`、`0`、`-1`、非法值 → **请求体不传 `max_tokens`**，由模型提供商 / 模型的默认上限决定；仅正整数时平台才会附带 `max_tokens`。kimi-k2.6 / Moonshot 等长上下文模型通常建议不设 cap（即不传）。

## 集成与流式

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/integrations/bridge/complete` | Local Bridge / 外部工具异步回传 run 结果；可选请求头 `X-Octopus-Bridge-Key`（与 `OCTOPUS_BRIDGE_SHARED_SECRET` 一致） |
| GET | `/tasks/{task_id}/events/stream` | **SSE**：任务事件（轮询式增量，约 0.5s 间隔） |
| GET | `/runs/{run_id}/logs/stream` | **SSE**：运行日志行（按 `seq` 增量） |

## Kanaloa / 平台能力（只读，无密钥）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/system/capabilities` | 平台版本、Kanaloa 权限列表、Agent/Skill 摘要、适配器实时摘要、Bridge 探测时间 |
| GET | `/api/adapters/status` | Claude Code / Cursor / Local Bridge / OpenClaw 健康状态与原因（诚实口径） |
| GET | `/api/agents/registry` | 统一 Agent registry 视图 |
| POST | `/api/adapters/claude-code/dispatch` | Claude 适配器：`mode=dry_run`（默认）或 `execute`（需已启用 `claude_code` Agent）。**权限档**：`owner` 下 `execute` 默认允许排队执行，**不**把 `OCTOPUS_KANALOA_ADAPTER_EXECUTE` 当作永久硬门槛；`safe` 下外部 `execute` **另外需要** `OCTOPUS_KANALOA_ADAPTER_EXECUTE=1`；`readonly` 禁止执行。`dry_run` 仅在用户/调用方明确 dry_run、只计划、不执行时使用。 |

## Kanaloa Action Gateway（P1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/kanaloa/actions/create-task` | Body：`agent_id`、`instruction`、`mode`（`dry_run`\|`execute`）、可选 `workspace`；走权限门与任务生命周期。与上表相同：**owner** 默认可 `execute`；**safe** 需 `OCTOPUS_KANALOA_ADAPTER_EXECUTE`；**readonly** 禁止；**dry_run** 仅明确演练/不执行时。 |
| POST | `/api/kanaloa/actions/dispatch` | Body：`task_id`；对已指派任务调用 `run_task` |
| GET | `/api/kanaloa/actions/task/{task_id}` | 任务详情（`tasks.read`） |
| GET | `/api/kanaloa/actions/task/{task_id}/events` | 任务事件（`tasks.read` + `audit.read`） |
| POST | `/api/kanaloa/actions/cancel` | Body：`task_id`；取消任务 |
| GET | `/api/kanaloa/actions/agents` | Agent 列表（`agents.list`） |
| GET | `/api/kanaloa/actions/recent-tasks` | 最近平台任务摘要（`tasks.read`） |

### Kanaloa Orchestrator（P3）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/kanaloa/orchestrator/run` | Body：`instruction`、`conversation_id?`、`subtask_mode`（`execute`\|`dry_run`）；**异步受理**：立即返回 `master_task_id`、`status=queued`、`message`；编排循环在后台执行。客户端轮询 `GET /api/kanaloa/orchestrator/tasks/{master_task_id}` 获取进度与 `final_summary`（`readonly` 拒绝） |
| GET | `/api/kanaloa/orchestrator/tasks` | 最近 master 任务列表（`tasks.read`） |
| GET | `/api/kanaloa/orchestrator/tasks/{master_task_id}` | Master 详情 |
| GET | `/api/kanaloa/orchestrator/tasks/{master_task_id}/events` | Master 编排事件时间线（`tasks.read` + `audit.read`） |
| POST | `/api/kanaloa/orchestrator/tasks/{master_task_id}/continue` | 继续执行未完成子任务（Body 可选 `subtask_mode`）；**异步受理**，立即返回 `master_task_id` / `status=queued`，后台继续执行；轮询同上 |
| POST | `/api/kanaloa/orchestrator/tasks/{master_task_id}/cancel` | 取消 master 并尝试取消未完成平台任务（`tasks.cancel`） |

可选环境变量：`OCTOPUS_KANALOA_SCOPES`（逗号分隔，收窄 Kanaloa 默认权限）。

## 健康与可观测

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 服务、`persistence`、`api_data_dir`、任务/run 计数、Bridge 是否可达、handoff 等待数等 |
| GET | `/metrics` | 聚合指标（任务、对话、run、Agent、Bridge 探测等） |
| GET | `/watchdog` | Watchdog 摘要（Bridge、滞留 handoff、失败 run 等） |

## Agent、Bridge、API Profile

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agents` | Agent 列表（持久化） |
| GET | `/agents/{agent_id}` | 单条 Agent + `bridge_state` + `api_profile` |
| POST | `/agents` | 创建 |
| PATCH | `/agents/{agent_id}` | 更新 |
| DELETE | `/agents/{agent_id}` | 删除（内置 Agent 受限，见实现） |
| POST | `/agents/{agent_id}/test-run` | 内置/外部测试运行入口 |
| GET | `/local-bridge` | 已注册 Bridge Agent 状态 |
| POST | `/local-bridge/probe` | 探测 Bridge |
| POST | `/local-bridge/register` | 注册 Bridge 侧 Agent |
| POST | `/local-bridge/result` | Bridge 结果入口（与生命周期集成） |
| GET | `/api-profiles` | LLM/API Profile 列表 |
| POST | `/api-profiles` | 创建/更新 Profile |
| GET | `/api-profiles/{profile_id}` | 单条 |
| POST | `/agents/{agent_id}/api-profile` | 绑定 Agent 与 Profile |

## 对话（Everyday）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversations` | 列表 |
| POST | `/conversations` | 创建 |
| GET | `/conversations/{id}` | 详情（含消息） |
| PATCH | `/conversations/{id}` | 更新 |
| DELETE | `/conversations/{id}` | 删除（可选级联 memory） |
| POST | `/conversations/{id}/messages` | 追加消息 |
| POST | `/conversations/{id}/promote` | 升格为任务 |

## 任务与运行

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 任务列表 |
| POST | `/tasks` | 创建任务 |
| GET | `/tasks/{task_id}` | 详情 + 指派历史 |
| POST | `/tasks/{task_id}/assign` | 指派 Agent |
| POST | `/tasks/{task_id}/run` | 创建 run 并入队（worker 异步执行；外部 Agent 走 Bridge） |
| POST | `/tasks/{task_id}/retry` | 重试 |
| POST | `/tasks/{task_id}/fail` | 标记失败 |
| POST | `/tasks/{task_id}/approve` | 审批通过 |
| POST | `/tasks/{task_id}/reject` | 审批拒绝 |
| GET | `/tasks/{task_id}/timeline` | 事件时间线 |
| GET | `/tasks/{task_id}/plan` | 执行计划视图 |
| GET | `/runs` | Run 列表 |
| GET | `/runs/{run_id}` | 单条 Run |

## 技能、账号、凭证、记忆、文件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/skills` | 技能列表（受 `skill_visibility` 过滤） |
| POST | `/skills/{skill_id}/execute` | 执行技能 |
| PATCH | `/skills/{skill_id}` | 更新 |
| DELETE | `/skills/{skill_id}` | 删除 |
| POST | `/skills/{skill_id}/publish` | 发布流程 |
| GET | `/accounts` | 账号元数据列表 |
| GET | `/credentials` | 凭证引用列表 |
| POST | `/credentials` | 写入凭证（密钥类字段多为 write-only） |
| GET | `/memory` | 记忆条目 |
| GET | `/memory/candidates` | 候选记忆 |
| POST | `/memory/candidates/{id}/approve` | 批准入库 |
| POST | `/memory/candidates/{id}/reject` | 拒绝 |
| DELETE | `/memory/{memory_id}` | 删除 |
| GET | `/memory/export` | 导出 |
| GET | `/files` | 文件制品列表 |
| POST | `/files` | 上传元数据/登记 |
| DELETE | `/files/{file_id}` | 删除 |

## 策略、通知、报告、监督与治理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/policies` | 执行策略列表 |
| GET | `/policies/explain` | 策略说明 |
| POST | `/policies` | 写入策略 |
| GET | `/notifications/channels` | 通知渠道 |
| POST | `/notifications/channels` | 配置渠道 |
| GET | `/notifications/deliveries` | 投递记录 |
| GET | `/reports` | 报告列表 |
| GET | `/reports/{report_id}` | 报告详情 |
| POST | `/reports/generate` | 生成报告 |
| GET | `/observer` | Observer 摘要 |
| GET | `/advisor` | Advisor 摘要 |
| GET | `/advisor/suggestions` | 建议列表 |
| GET | `/advisor/tasks/{task_id}` | 任务维度建议 |
| POST | `/advisor/suggestions/{id}/accept` | 接受建议 |
| POST | `/advisor/suggestions/{id}/dismiss` | 忽略建议 |
| POST | `/runtime/supervision/run` | 触发一次监督周期（由环境开关控制） |
| GET | `/governor` | Governor 摘要 |
| GET | `/governor/decisions` | 决策列表 |
| GET | `/governor/decisions/{decision_id}` | 单条决策 |
| POST | `/governor/evaluate` | 评估 |
| POST | `/governor/decisions/{decision_id}/confirm` | 确认决策 |
| GET | `/escalations` | 升级事件 |
| POST | `/escalations/{event_id}/acknowledge` | 确认 |
| POST | `/escalations/{event_id}/resolve` | 解决 |

> **`GET /watchdog`**：见上文「健康与可观测」表（与 `/metrics` 并列）。

## 响应字段说明

多数 JSON 响应带有 `version`（如 `"1.1.0"`）字段，标识平台对齐版本，不代表响应为内存假数据。列表类接口使用 `ListResponse`（`items` + 可选 `version` / `note` / 分页字段）；请以 OpenAPI 与各路由实际实现为准。策略与报告实体使用字段 **`is_draft`**（草稿 / 未生效）而非演示数据标记。

### 列表分页与限流（防止越用越卡）

- `GET /tasks`、`/runs`、`/memory`、`/reports`、`/notifications/deliveries`（及旧版 `/v1/tasks`、`/v1/memory`）支持 `limit`（默认 200，最大 1000）与 `offset`（默认 0）查询参数，按时间倒序返回，响应附带 `total` / `limit` / `offset`。
- `GET /tasks/{task_id}/timeline` 支持 `events_limit`（默认 500）与 `logs_limit`（默认 1000），默认返回**最近** N 条并附带 `events_total` / `run_logs_total`。
- `GET /runs/{run_id}` 支持 `logs_limit`（默认 1000），默认返回最近 N 条日志并附带 `logs_total`。

未传分页参数时行为向后兼容（仅在数据量超过默认上限时才截断，避免无界响应）。

## 未在本文逐项展开的详情

以仓库内 `apps/api/app/routes/v2/platform.py` 与 OpenAPI (`/docs`) 为权威来源；新增路由时请先更新实现再同步本文件。
