# BETA_LIMITATIONS（公开免费 Beta 诚实边界）

本仓库 **Public Free Beta** 的对外说明以仓库根目录 [`README.md`](../../../../README.md) 与本文档为准（另见 [`docs/BETA_LIMITATIONS.md`](../../../../docs/BETA_LIMITATIONS.md)）。内部母本规格与验收清单不在公开镜像中提供。

---

## 本轮 Beta 收口（2026-04-22）已完成

- **技能列表无 `[MOCK]`**：种子数据与 `apps/api/data/skills.json` 已清理；`skill_visibility` + 列表 API（含 `/v1/skills`、v2 skills）过滤 `[MOCK]` / `is_mock`；执行不可见技能返回 404。
- **报告列表无占位 mock**：`reports` 列表 API 与数据侧对齐用户可见性过滤。
- **`/notifications` 独立页面**：`apps/web/src/app/notifications/page.tsx` 调用真实 `GET /notifications/channels`；启用/禁用走 `POST /notifications/channels`（若环境无写权限或接口变更，以页面标注为准）。
- **设置与导航**：`Settings` 保留通知摘要并含「查看全部」→ `/notifications`；侧栏含 **Notifications**（Bell 图标）。
- **默认执行策略**：仓库内默认全局策略为 **`mode: auto`**、`is_mock: false`，避免干净启动后所有运行卡在 `waiting_approval`（此前 `confirm` 会强制审批）。用户仍可通过 `/policies` 收紧为 `confirm` / `notify`。
- **自动化验证（本会话已真实执行）**：
  - `npm run build:web`：**通过**
  - `apps/api` 下 `pytest`：**6 passed**
  - `.\scripts\run-web-prod-e2e.ps1`：**通过**（**5** 个 Playwright 用例，含 Local Agent 控制面；证据可由脚本重新生成至 `reports/web-prod-e2e-*.log`）

---

## 真实完成（可运行、可对外演示）

- **执行模式（UI 文案）**：`direct_agent` 在 Kanaloa 上为 **内置直连**，在外部 Agent 上为 **外部直连**；`commander` 为 **统筹执行**；`pilot` 为 **追踪执行**（仅 Kanaloa；外部操作者不展示「追踪执行」）。
- 任务生命周期：`POST /tasks` → `assign` → `run` →（可选）`retry` / `fail`
- 文件持久化：`apps/api/data/*.json`（Beta 可接受；非企业级 DB）
- 可选 PostgreSQL：`OCTOPUS_PERSISTENCE=postgres` + Alembic；schema 为 JSONB 兼容层，非 PRD 终局拆表（见 [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md)）
- 内置执行体：`octopus_builtin` 同步执行（结构化输出，无外部 LLM）
- Local Bridge：`POST /v1/execute` 真实 HTTP；**Claude Code** 若存在 `claude` CLI 可走 `claude -p`；否则写 **handoff** 文件
- OpenClaw：若配置 `OPENCLAW_WEBHOOK_URL` 则真实 HTTP POST；否则 handoff
- Cursor：**不宣称**全量无头自动化；默认 **handoff** + 可选检测 `cursor --version`
- 回调：`POST /integrations/bridge/complete` 结束 `waiting_approval` 类任务
- 监控：`GET /metrics`、`GET /watchdog`（Beta 规则）

---

## Beta 级 / 未完成生产加固（不可宣称为正式版能力）

- **无** OAuth / 第三方开发者应用注册流程
- **无** 支付 / 订阅
- **无** 生产级密钥仓（KMS/Keychain）与完整多租户隔离
- **无** 企业审计与细粒度 RBAC
- Bridge 鉴权仅为可选共享密钥（`OCTOPUS_BRIDGE_SHARED_SECRET`）
- 通知投递：**不保证**生产 SLA；频道管理为 Beta 能力边界

---

## 占位 / 未宣称完成

- 全自动“遥控”Cursor/OpenClaw/任意桌面 GUI（除非用户环境真实具备 CLI/Webhook）
- App Store / 桌面安装器发布
- 生产级高可用、备份、合规认证
- PRD 全量移动端原生 App、操控舱单页五区字面还原

---

## 数据迁移路径（离开文件存储）

下一阶段建议 PostgreSQL + 迁移工具；任务/事件/Run/日志与 [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) 对齐。

---

## 不能宣称为正式版能力的摘要

凡上列 **「Beta 级 / 未完成生产加固」** 与 **「占位 / 未宣称完成」** 中的条目，均不得在产品对外话术中标为「正式版 / 生产就绪 / 已全面完成」。
