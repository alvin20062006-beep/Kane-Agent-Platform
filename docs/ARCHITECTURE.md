# ARCHITECTURE（实现概览）

本文描述仓库 **当前** 的分层与主要组件，与运行中的 **API / Web / Local Bridge** 一致；不以「冻结骨架」为借口将已实现能力写成占位。

## 目录结构

```
octopus-platform/
  apps/
    api/           FastAPI 控制面：任务/对话/run/事件/策略/凭证/技能/报告等
    web/           Next.js 控制台 UI
    local-bridge/  可选：本机执行适配（CLI / Webhook / handoff / 本地脚本）
  packages/
    schemas/       共享 JSON Schema
    core/          共享 Python 库（如任务状态机）
  docs/            公开文档
```

## 数据持久化

- **默认**：`OCTOPUS_PERSISTENCE=file`，JSON 文件仓库（数据目录见 `/health` 的 `api_data_dir`）。
- **可选**：`OCTOPUS_PERSISTENCE=postgres` + `DATABASE_URL`，实体落在 `octopus_entities` 等表（JSONB 载荷），与文件模式共用同一仓储抽象。

## 组件关系（简图）

- **Web** 通过 `NEXT_PUBLIC_API_BASE_URL` 调用 **API** 的 REST（及浏览器侧 SSE）。
- **API** 内 **worker** 线程从队列消费待执行 run，按 Agent 适配类型调用内置执行器或 **HTTP 调用 Local Bridge** 的 `/v1/execute`。
- **Local Bridge** 可选择性将结果 **POST** 回 `POST /integrations/bridge/complete`。
- **策略引擎**、**Advisor / Governor / Observer**、**Watchdog 指标** 在 API 进程内组合使用，持久化仍走同一 store。

## 已实现能力与诚实边界

- **任务**：创建、指派、运行、重试、失败、审批门、时间线、执行计划。
- **Run / 日志 / 事件**：持久化；SSE 流为轮询式增量，非高吞吐实时总线。
- **技能**：注册表 + `execute` 路径（具体技能行为因 skill 而异）。
- **外部 Agent**：依赖 Bridge + 本机工具（Claude CLI、Webhook、handoff）；详见 `docs/EXTERNAL_AGENT_INTEGRATION.md`。
- **生产级多租户 / OAuth / KMS**：未作为本项目开箱能力宣称；单机与实验室内网部署为主。

## 延伸阅读

- `docs/API.md` — HTTP 路由表
- `docs/LOCAL_BRIDGE.md` — Bridge 行为与安全边界
- `docs/DATABASE_SCHEMA.md` — 存储模型与 Postgres 兼容说明
