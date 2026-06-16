# Local Bridge

在 **本机或内网** 运行的 FastAPI 服务，供 **Octopus API** 通过 HTTP 调用以执行「外部适配器」类任务（Claude CLI、OpenClaw Webhook、本地脚本、Cursor handoff 等）。实现见 `app/main.py`。

## 运行

```bash
cd apps/local-bridge
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

- 健康检查：`GET http://127.0.0.1:8010/health`
- 状态：`GET http://127.0.0.1:8010/v1/status`

## 主要 HTTP 端点

| 路径 | 说明 |
|------|------|
| `GET /health` | 存活 |
| `GET /v1/status` | 注册数、PATH 探测、OpenClaw 是否配置等 |
| `POST /agents/register` | 注册 Agent |
| `POST /agents/heartbeat` | 心跳 |
| `GET /agents`、`GET /agents/{id}` | 查询 |
| `POST /v1/execute` | API 发起的同步执行（需与任务侧 `adapter_id` 一致） |
| `POST /tasks/result`、`GET /tasks/results` | 结果回传与查询 |

完整说明与环境变量见仓库根目录 **`docs/LOCAL_BRIDGE.md`** 与 **`docs/EXTERNAL_AGENT_INTEGRATION.md`**。

## 环境变量

| 变量 | 作用 |
|------|------|
| `OCTOPUS_API_PUBLIC_URL` | 回调 API 基址，默认 `http://127.0.0.1:8000` |
| `OCTOPUS_BRIDGE_SHARED_SECRET` | 可选；设置时 **`register` 与 `/v1/execute`** 需 `X-Octopus-Bridge-Key`；`heartbeat` 与 `GET /agents` 等当前不校验 |
| `OPENCLAW_WEBHOOK_URL` | 可选；`openclaw_http` 适配器 POST 目标 |
