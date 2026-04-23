# BETA_CHECKLIST（验收清单）

## 本地

- [ ] `apps/api` 启动，`GET /health` → `{"status":"ok"}`
- [ ] `apps/local-bridge` 启动，`GET /health` → ok
- [ ] `apps/web` 启动，打开 `/cockpit`
- [ ] Cockpit：**创建 → 分配 → 运行** 成功（内置 Agent）
- [ ] `GET /tasks/{id}/timeline` 含 events / runs / run_logs
- [ ] `GET /metrics`、`GET /watchdog` 有数据
- [ ] 外部 Agent：启动 Bridge，选择 `claude_code_external` 运行；观察 CLI 或 handoff + callback 文档路径

## VPS（见 DEPLOYMENT_VPS.md）

- [ ] 防火墙开放 3000/8000/8010（或反代）
- [ ] 设置 `NEXT_PUBLIC_API_BASE_URL` 指向公网 API
- [ ] 设置 `OCTOPUS_API_PUBLIC_URL` 为 Bridge 可访问的 API 地址

## 诚实性

- [ ] 阅读 `docs/BETA_LIMITATIONS.md`，不向投资人/用户夸大自动化范围
