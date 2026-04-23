# VERIFY（本地验证清单）

本清单用于验证 **Public Free Beta**：API / Web / Local Bridge 可运行，**真实任务流**与 **Timeline** 可见，外部 Agent 路径诚实可用（CLI / Webhook / handoff）。

## 方式 A：本机直接运行

### 1) 安装 Node workspace 依赖

```bash
cd <repo-root>
npm install
```

### 2) 运行 API

```bash
cd apps/api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

验证：

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/docs`

### 3) 运行 Local Bridge（Beta：真实 /v1/execute）

```bash
cd apps/local-bridge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

验证：

- `GET http://127.0.0.1:8010/health`

### 4) 运行 Web

```bash
cd apps/web
npm run dev
```

打开浏览器：

- `http://localhost:3000`

### 5) 验证真实任务流（API）

```bash
# 创建
curl -s -X POST http://127.0.0.1:8000/tasks -H "content-type: application/json" -d "{\"title\":\"CLI smoke\",\"description\":\"hello\"}"

# 记下 task_id 后：
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/assign -H "content-type: application/json" -d "{\"agent_id\":\"octopus_builtin\"}"
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/run
curl -s http://127.0.0.1:8000/tasks/TASK_ID/timeline
```

外部 Agent（需 Bridge 启动，agent 选 `claude_code_external` 等）：

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/assign -H "content-type: application/json" -d "{\"agent_id\":\"claude_code_external\"}"
curl -s -X POST http://127.0.0.1:8000/tasks/TASK_ID/run
```

### 6) 监控

```bash
curl -s http://127.0.0.1:8000/metrics
curl -s http://127.0.0.1:8000/watchdog
```

## 方式 B：Docker Compose（可选）

> 说明：仅用于本地快速查看，不代表生产部署完成。

```bash
docker compose up --build
```

打开：

- Web：`http://localhost:3000`
- API docs：`http://localhost:8000/docs`
- Bridge health：`http://localhost:8010/health`

## 构建/自检

```bash
cd <repo-root>
npm run build:web
npm run test:api
```

