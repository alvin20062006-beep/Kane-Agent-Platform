# API_ROUTE_INVENTORY（以实现为准）

> 来源：以 `apps/api/app/routes/**` 的实现为事实来源（而非文档设想）。  
> 标注说明：
> - **real**：端点真实工作、读写真实持久化（file store），可被脚本验证
> - **beta-limited**：真实工作，但能力边界为 Beta（如弱鉴权、handoff 需人工、同步执行等）
> - **incomplete**：端点存在但语义/数据不完整或仍为 mock/占位

## Base

- **API app**：`apps/api/app/main.py`
- **Routes**
  - `apps/api/app/routes/health.py`
  - `apps/api/app/routes/integrations.py`
  - `apps/api/app/routes/v2/platform.py`（主 Beta 路由）
  - `apps/api/app/routes/resources.py`（`/v1/*` legacy 别名，与主路由同源持久化）

---

## Health & Monitoring

### GET `/health` — **real**

- **Response**：`{ status, service, beta, tasks_total, runs_total, local_bridge_reachable, waiting_handoffs }`
- **Notes**：聚合 `metrics + watchdog`，用于健康检查（beta-limited：不含深度依赖探测）。

### GET `/metrics` — **real (beta-limited)**

- **Response**：聚合 tasks/runs/agents/local_bridge/fault_recovery 等计数与摘要
- **Notes**：beta-limited（非 Prometheus 格式；无 worker/queue）。

### GET `/watchdog` — **real (beta-limited)**

- **Response**：`WatchdogStatus { summary, events, recovery_hints }`
- **Notes**：beta 规则（15min stalled、bridge health、waiting handoffs 等）。

---

## Agents

### GET `/agents` — **real**

- **Response**：`ListResponse<Agent>`

### GET `/agents/{id}` — **real (beta-limited)**

- **Response**：`{ data: Agent, bridge_state, api_profile? }`
- **Notes**：bridge_state 依赖 API-side registry（非直接探测 bridge /agents）。

### POST `/agents` — **real (beta-limited)**

- **Body**：`AgentCreateBody`（含 `integration_mode` / `control_plane` 等）
- **Persists**：`agents.json`

### PATCH `/agents/{id}` — **real (beta-limited)**

- **Body**：`AgentPatchBody`（部分字段；`control_plane` 与存量合并）

### POST `/agents/{agent_id}/test-run` — **real (beta-limited)**

- **Behavior**：创建短任务 → assign → `run`（队列）；返回 `task_id` / `run_id`；handoff 类可能停在 `waiting_approval`。

---

## Tasks (Lifecycle)

### GET `/tasks` — **real**

- **Response**：`ListResponse<Task>`

### GET `/tasks/{id}` — **real**

- **Response**：`{ data: Task, assignments: TaskAssignment[] }`

### POST `/tasks` — **real**

- **Body**：`{ title, description?, execution_mode }`
- **Response**：`{ data: Task }`
- **Persists**：`tasks.json` + `task_events.json (task_created)`

### POST `/tasks/{id}/assign` — **real**

- **Body**：`{ agent_id }`
- **Response**：`{ data: Task }`
- **Persists**：`task_assignments.json` + `task_events.json (agent_assigned)`

### POST `/tasks/{id}/run` — **real (beta-limited)**

- **Response**：`{ ok, task, run, integration_path, output?, error?, pending_handoff? }`
- **Persists**：`runs.json` + `run_logs.json` + `task_events.json`
- **Notes**：beta-limited（同步执行；外部 agent 走 Local Bridge；handoff 会进入 waiting_approval）。

### POST `/tasks/{id}/retry` — **real**

- **Response**：`{ data: Task }`
- **Persists**：`task_events.json (retry_requested)`

### POST `/tasks/{id}/fail` — **real (beta-limited)**

- **Body**：`{ reason }`
- **Response**：`{ data: Task }`
- **Notes**：operator recovery 入口，强制置 failed。

### GET `/tasks/{id}/timeline` — **real**

- **Response**：`{ task, assignments, events, runs, run_logs }`
- **Notes**：Cockpit/Task Detail 的事实来源（持久化回放）。

---

## Runs

### GET `/runs` — **real**

- **Response**：`{ items: Run[] }`

### GET `/runs/{id}` — **real**

- **Response**：`{ data: Run, logs: RunLogLine[] }`

---

## Skills / Accounts / Credentials / Memory

### GET `/skills` — **real (beta-limited)**

- **Response**：`ListResponse<Skill>`
- **Notes**：包含 builtin 与部分 mock skills；真实可执行 skills 见 `/skills/{id}/execute`。

### POST `/skills/{id}/execute` — **real (beta-limited)**

- **Body**：`SkillExecuteBody { input: object }`
- **Response**：`SkillExecuteResult { ok, skill_id, output, error? }`
- **Persists**：会追加 `task_events` 与 `run_logs`（审计用，beta-limited：不做复杂回滚）
- **Notes**：当前实现至少包含：
  - `skill_text_summarize`（builtin，无外部调用）
  - `skill_http_request`（真实 HTTP outbound，支持 `credential_ref` Bearer）

### GET `/accounts` — **real (beta-limited)**

- **Response**：`ListResponse<Account>`

### GET `/credentials` — **real (beta-limited)**

- **Response**：`ListResponse<Credential>`（`secret_material` 强制为 null）

### POST `/credentials` — **real (beta-limited)**

- **Body**：`CredentialUpsertBody`
- **Response**：返回 `Credential` 但 `secret_material` 不回显，仅返回 `credential_ref` 与 `masked_hint`

### GET `/memory` — **real (beta-limited)**

- **Response**：`ListResponse<MemoryItem>`

### GET `/memory/candidates` — **real**

- **Response**：候选项过滤（`status=candidate`）

### POST `/memory/candidates/{id}/approve` — **real (beta-limited)**

- **Response**：`{ ok, data }`（无鉴权/审计）

### POST `/memory/candidates/{id}/reject` — **real (beta-limited)**

- **Response**：同上

---

## Policies

### GET `/policies` — **real (beta-limited)**

- **Response**：`ListResponse<ExecutionPolicy>`
- **Notes**：读写路径存在；执行时会进行最小 policy gate 与 approval（beta-limited）。

### POST `/policies` — **real (beta-limited)**

- **Body**：`ExecutionPolicyUpsertBody`
- **Response**：`{ ok, data: ExecutionPolicy }`

---

## Notifications

### GET `/notifications/channels` — **real (beta-limited)**

- **Response**：`ListResponse<NotificationChannel>`

### POST `/notifications/channels` — **real (beta-limited)**

- **Body**：`NotificationChannelUpsertBody`
- **Notes**：当前最小可用通道为 webhook（best-effort）；投递记录写入 deliveries

### GET `/notifications/deliveries` — **real (beta-limited)**

- **Response**：`ListResponse<NotificationDelivery>`

---

## Agent API Profiles

### GET `/api-profiles` — **real (beta-limited)**

- **Response**：`ListResponse<AgentApiProfile>`（api_key 会被 mask）

### POST `/api-profiles` — **real (beta-limited)**

- **Body**：`AgentApiProfileUpsertBody`

### GET `/api-profiles/{id}` — **real (beta-limited)**

- **Response**：`{ data: AgentApiProfile }`（api_key mask）

### POST `/agents/{agent_id}/api-profile` — **real (beta-limited)**

- **Body**：`AgentApiBindingBody`
- **Notes**：把 profile 绑定到指定 agent，executor/bridge 执行时会 resolve 并下发（bridge 侧使用明文 key）

---

## Local Bridge

### GET `/local-bridge` — **real (beta-limited)**

- **Response**：bridge reachability + API-side registry

### POST `/local-bridge/probe` — **real (beta-limited)**

- **Response**：对 Bridge `/health` 与 `/v1/status` 的即时探测 + `hints`（供前端连接向导）

### POST `/local-bridge/register` — **real (beta-limited)**

- **Body**：`LocalBridgeRegisterBody`
- **Notes**：写入 `local_bridge.json`

### POST `/local-bridge/result` — **real (beta-limited)**

- **Body**：`LocalBridgeResultBody`
- **Notes**：用于外部 agent 的“结果回灌”路径（与 `/integrations/bridge/complete` 并存）。

### POST `/integrations/bridge/complete` — **real (beta-limited)**

- **Body**：`BridgeCompleteBody`
- **Auth**：可选 `X-Octopus-Bridge-Key`（由 `OCTOPUS_BRIDGE_SHARED_SECRET` 控制）

---

## Reports

### GET `/reports` — **real (beta-limited/incomplete)**

- **Response**：`ListResponse<Report>`
- **Notes**：同时包含 mock 与 real（real 由 `/reports/generate` 基于 runs/events/logs 生成）。

### GET `/reports/{id}` — **real (beta-limited/incomplete)**

- **Response**：`{ data: Report }`

### POST `/reports/generate` — **real (beta-limited)**

- **Body**：`{ type: "comparison", title? }`
- **Response**：`{ ok, data: Report }`
- **Notes**：会读取真实 runs/events/logs 生成统计摘要并落盘。

---

## Legacy `/v1/*`（与主 API 同源）

以下为 **向后兼容前缀**，数据与无 `/v1` 前缀的路由相同（文件或 Postgres 持久化），**非**独立内存 mock：

- GET `/v1/agents` — 同 `/agents`
- GET `/v1/tasks` — 同 `/tasks`
- GET `/v1/skills` — 同 `/skills`
- GET `/v1/accounts` — 同 `/accounts`
- GET `/v1/memory` — 同 `/memory`
- GET `/v1/watchdog` — 同 `/watchdog`（`build_watchdog_status`）

