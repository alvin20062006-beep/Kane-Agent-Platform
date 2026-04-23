# apps/local-bridge（Phase 3 skeleton）

本服务用于连接本地环境（Claude Code、本地脚本、浏览器 session 等）的“桥接层”。

**当前阶段仅提供占位服务**：

- `GET /health`
- `POST /agents/register`（占位，无鉴权）
- `POST /agents/heartbeat`（占位）
- `GET /agents`（占位）
- `POST /tasks/result`（占位）
- `GET /tasks/results`（占位）

> 注意：不代表 Claude Code / OpenClaw 已接入；目前无真实执行/转发。

## 运行

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

