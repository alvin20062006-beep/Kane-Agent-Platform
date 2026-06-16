# VERIFY（本地验证指南）

用于确认本仓库在单机上的 **依赖安装**、**前后端启动**、**API 健康**、**任务 / run / 事件 / 日志** 与（可选）**Local Bridge** 行为。以当前实现为准；若某一步失败，请对照 `apps/api`、`apps/web`、`apps/local-bridge` 的日志与 `http://127.0.0.1:8000/docs`。

**快捷命令（仓库根目录）：**

| 命令 | 前提 | 内容 |
|------|------|------|
| `npm run verify` | 无服务需在线 | API/Bridge 单测 + Web typecheck + lint |
| `npm run verify:live` | API + Bridge + Web 已启动 | task/bridge 脚本 + Playwright `smoke.spec.ts` |
| `npm run dev:stack` | — | 同时启动 API + Bridge + Web |
| `npm run wait:stack` | `dev:stack` 已启动 | 等待 8000/8010/3000 就绪 |
| `npm run test:e2e:smoke` | 同上 | 仅核心浏览器冒烟 |
| `npm run test:e2e` | 同上 | 完整 Playwright 套件 |

公开镜像 README 以 [`PUBLIC_REPO_README.md`](../PUBLIC_REPO_README.md) 为准。

## 0. 黄金路径（新用户 ~5 分钟连上外部 Agent）

**终端 A（仓库根目录）：**

```bash
npm install
npm run setup
npm run dev:stack
```

**终端 B（等待栈就绪后）：**

```bash
npm run wait:stack
npm run verify:live
```

**浏览器：** 打开 `http://127.0.0.1:3000/local-bridge?connect=1`，使用「连接外部 Agent」向导（内置 `skill_connect_agent`）。推荐选 **HTTP/Webhook（通用）** → 预览 → 确认登记 → 查看试跑任务。

## 1. 安装 monorepo 依赖

```bash
cd <repo-root>
npm install
```

## 2. 启动 API（端口 8000）

```bash
cd apps/api
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**检查：**

- 浏览器或 `curl`：`GET http://127.0.0.1:8000/health` → JSON `status: ok`
- OpenAPI：`GET http://127.0.0.1:8000/docs`

（可选）仓库根目录亦可用：`npm run dev:api`（脚本假定 Windows 下 `apps/api\.venv\Scripts\python` 已存在）。

## 3. 启动 Web（端口 3000）

在单独终端：

```bash
# 设置浏览器可见的 API 地址，例如 PowerShell:
# $env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
cd apps/web
npm install
npm run dev
```

打开控制台打印的本地 URL（常为 `http://localhost:3000` 或 `http://127.0.0.1:3000`）。若 `localhost` 与 `127.0.0.1` 行为不一致，请与 `apps/web/next.config.ts` 中 `allowedDevOrigins` 对齐。

**检查：** 页面可加载；设置页或网络请求指向上述 API Base。

## 4.（可选）启动 Local Bridge（端口 8010）

外部适配类 Agent（如 Claude Code / OpenClaw / handoff 路径）需要 Bridge：

```bash
cd apps/local-bridge
python -m venv .venv
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

**检查：** `GET http://127.0.0.1:8010/health`，`GET http://127.0.0.1:8010/v1/status`。

API 进程环境中应设置 `OCTOPUS_LOCAL_BRIDGE_URL=http://127.0.0.1:8010`（默认值即此，若分端口需修改）。

## 5. 任务与运行（API）

以下示例使用 `curl`。创建任务的响应体为 `{"data": { "task_id": "...", ... }}`（另含兼容字段）；请将 `TASK_ID` 换为 **`data.task_id`**。

```bash
# 创建任务
curl -s -X POST http://127.0.0.1:8000/tasks -H "content-type: application/json" -d "{\"title\":\"verify-smoke\",\"description\":\"hello\"}"

# 指派内置或已存在 agent_id（请以 GET /agents 返回的 agent_id 为准）
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/assign -H "content-type: application/json" -d "{\"agent_id\":\"YOUR_AGENT_ID\"}"

# 运行（产生 run；由后台 worker 与执行器驱动）
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/run

# 时间线（任务事件）
curl -s http://127.0.0.1:8000/tasks/TASK_ID/timeline

# Run 列表与单条（从 timeline 或 GET /runs 取得 run_id）
curl -s http://127.0.0.1:8000/runs
curl -s http://127.0.0.1:8000/runs/RUN_ID
```

**期望：** `timeline` 中出现事件；`runs` 中 run 状态随执行推进（外部 Agent 可能为 `waiting_approval` 直至 handoff/回调完成）。

### 5.1 SSE（可选）

服务端为 **轮询式 SSE**（约 0.5s 间隔推送增量），可用原生命令行观察（示例）：

```bash
curl -N http://127.0.0.1:8000/tasks/TASK_ID/events/stream
curl -N "http://127.0.0.1:8000/runs/RUN_ID/logs/stream?since_seq=0"
```

按 `Ctrl+C` 结束。

## 6. Bridge 回调（外部路径）

若任务走 handoff，需按 handoff 或 `docs/EXTERNAL_AGENT_INTEGRATION.md` 调用：

`POST http://127.0.0.1:8000/integrations/bridge/complete`

（若配置共享密钥，附加头 `X-Octopus-Bridge-Key`。）

## 7. 聚合监控端点

```bash
curl -s http://127.0.0.1:8000/metrics
curl -s http://127.0.0.1:8000/watchdog
```

## 8. 构建与自动化测试（可选）

```bash
cd <repo-root>
npm run typecheck
npm run build:web
npm run test:api
```

端到端浏览器测试（需已按 Playwright 配置启动可达的 Web/API，见 `apps/web/playwright.config.ts`）：

```bash
npm run test:e2e
```

## 9. Docker Compose（可选）

仅用于本地编排，不等同生产高可用：

```bash
docker compose up --build
```

具体端口与 `NEXT_PUBLIC_API_BASE_URL` 见 `docker-compose.yml` 与各服务环境变量说明。
