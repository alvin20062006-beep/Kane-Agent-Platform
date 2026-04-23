# DEPLOYMENT_LOCAL（本地运行）

## 1. API

```bash
cd apps/api
python -m venv .venv
.\.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

验证：`http://127.0.0.1:8000/docs`

## 2. Local Bridge

```bash
cd apps/local-bridge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

验证：`http://127.0.0.1:8010/v1/status`

## 3. Web

```bash
cd apps/web
npm install
npm run dev
```

`apps/web/.env.local`：

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 4. 可选：共享密钥（Bridge ↔ API）

在 API 与 Bridge 进程环境中同时设置：

```
OCTOPUS_BRIDGE_SHARED_SECRET=change-me
```

请求头：`X-Octopus-Bridge-Key: change-me`

## 5. OpenClaw Webhook（可选）

Bridge 环境：

```
OPENCLAW_WEBHOOK_URL=https://your-endpoint
```
