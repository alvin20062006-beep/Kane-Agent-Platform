# Local Bridge（可选本地执行适配器）

**Local Bridge** 是运行于本机（或内网）的 **FastAPI** 小服务（默认端口 **8010**），由 **`apps/api`** 在运行外部适配类 Agent 时通过 HTTP 调用。它不是独立产品进程「占位」，而是包含 **真实执行与回传路径**：可选 Claude CLI、OpenClaw HTTP、`local_script`  shell、Cursor handoff 文件等（见 `apps/local-bridge/app/main.py`）。

## 当前实现概要

- **进程内状态**：已注册 Agent、心跳、最近执行结果等可持久化到 `apps/local-bridge/data/*.json`（注意 `.gitignore`）。
- **鉴权（可选）**：若设置 `OCTOPUS_BRIDGE_SHARED_SECRET`，则 **`POST /agents/register`** 与 **`POST /v1/execute`** 需提供请求头 `X-Octopus-Bridge-Key`。**`POST /agents/heartbeat`、`GET /agents`、`GET /agents/{agent_id}` 在当前实现中不校验该密钥**（仅应在可信网络中使用）。
- **与 API 回调**：Bridge 完成或部分路径会请求 API 的 `POST /integrations/bridge/complete`（Base URL 由 `OCTOPUS_API_PUBLIC_URL` 决定）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `OCTOPUS_BRIDGE_SHARED_SECRET` | 可选；与 API 侧一致时，**仅** `POST /agents/register` 与 `POST /v1/execute` 需 `X-Octopus-Bridge-Key`；heartbeat 与只读 `GET /agents*` 不校验 |
| `OCTOPUS_API_PUBLIC_URL` | Bridge 回调 API 的基址，默认 `http://127.0.0.1:8000` |
| `OPENCLAW_WEBHOOK_URL` | 可选；`openclaw_http` 适配器将任务 JSON POST 到此 URL；未配置时写入 handoff 文件 |

## HTTP 端点（实现现状）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 存活检查 |
| GET | `/v1/status` | 已注册 Agent 数、heartbeats、`openclaw_configured`、`claude`/`cursor` 是否在 PATH、handoff 目录等 |
| POST | `/agents/register` | 注册 Agent（可选 Bridge Key） |
| POST | `/agents/heartbeat` | 心跳 |
| GET | `/agents` | 列出注册与心跳 |
| GET | `/agents/{agent_id}` | 单条 + 近期结果 |
| POST | `/v1/execute` | **API 调用的同步执行**：按 `adapter_id` 分支（见下文） |
| POST | `/tasks/result` | 回传结果；若带 `run_id` 会尝试 POST API `/integrations/bridge/complete` |
| GET | `/tasks/results` | 最近结果记录 |

## `POST /v1/execute` 与外部工具（诚实边界）

请求体包含 `task_id`、`run_id`、`agent_id`、`adapter_id`、`title`、`description`、`execution_mode`、`api_profile`、`agent_control_plane` 等（见 `ExecutePayload`）。

| `adapter_id` | 行为 |
|--------------|------|
| `claude_code` | 若存在 `claude` 可执行文件：尝试 `claude -p <prompt>`（非交互，超时 120s）。否则：在 `data/handoffs/` 写入 **handoff** markdown，并提示通过 API `bridge/complete` 人工回传 |
| `openclaw_http` | 若配置 `OPENCLAW_WEBHOOK_URL`：`httpx.post` JSON 到该 URL。否则：写 OpenClaw handoff 文件 |
| `cursor_cli` | 写 Cursor handoff 文件；可选执行 `cursor --version` 探测；**不保证**无头全自动 IDE |
| `local_script` | 从 `agent_control_plane.shell_command` 或任务正文解析命令，在 Bridge 主机上 `subprocess.run`（**本地命令执行有风险**，仅应在受信环境使用） |
| 其他 | 返回 `unsupported_adapter` |

集成细节与推荐联调步骤见 **`docs/EXTERNAL_AGENT_INTEGRATION.md`**。

## 安全边界（简表）

- Bridge 能对 **本机** 执行 shell（`local_script`）与启动 CLI；应仅在受信网络或本机运行。
- `OCTOPUS_BRIDGE_SHARED_SECRET` 为**轻量共享口令**，不能替代完整 mTLS 或零信任架构。
- Handoff 文件可能含任务描述与回调说明，注意文件权限与清理。

## 运行方式

```bash
cd apps/local-bridge
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

API 侧需能访问 Bridge（默认 `OCTOPUS_LOCAL_BRIDGE_URL=http://127.0.0.1:8010`）。

更详细的命令与变量表见 **`apps/local-bridge/README.md`**。
