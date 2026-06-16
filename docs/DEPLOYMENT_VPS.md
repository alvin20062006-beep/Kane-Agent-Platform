# DEPLOYMENT_VPS（VPS / 单节点）

> 以下为 **单节点** Compose 或手工多进程的典型摆法，**不**等于高可用生产模板。

## 架构

- **API**：8000
- **Web**：3000
- **Local Bridge**：8010（与 API 同机或同内网）

## 环境变量（示例）

`/etc/octopus.env`：

```
NEXT_PUBLIC_API_BASE_URL=http://YOUR_PUBLIC_IP:8000
OCTOPUS_API_PUBLIC_URL=http://YOUR_PUBLIC_IP:8000
OCTOPUS_LOCAL_BRIDGE_URL=http://127.0.0.1:8010
OCTOPUS_BRIDGE_SHARED_SECRET=use-long-random
OPENCLAW_WEBHOOK_URL=
```

## Docker Compose

仓库根目录：

```bash
docker compose up -d
```

默认 Compose 内 Web 的 `NEXT_PUBLIC_API_BASE_URL` 可能指向 `http://api:8000`（容器网络）。若浏览器在集群外访问，请改为 **公网或域名可达的 API 地址** 并重建 Web 镜像/服务。

## 反代

使用 Caddy/Nginx 等终止 TLS，反代到 `web:3000` 与 `api:8000`；Bridge 建议仅内网或本机可达。

## 验证

- `GET /health`、`GET /metrics`、`GET /watchdog`
- 浏览器打开 Web，走对话 / 任务 / 设置 等流程
