# ARCHITECTURE（Phase 0 冻结）

本文件描述 **Phase 0 + Phase 1 foundation** 的可运行骨架，以及与 PRD 十层架构的映射关系。  
注意：本阶段不实现外部 Agent 真接入、OAuth、浏览器自动化、生产数据库；仅提供**协议与占位流**。

## 目标（本阶段）

- 本地可启动：API + Web
- Web 可视化：8 个导航页面可访问
- API 可用：健康检查与 6 个资源列表端点返回 **MOCK 数据**
- 共享 schemas：用于前后端对齐字段命名与未来协议演进

## 目录结构（本阶段）

```
octopus-platform/
  apps/
    api/        FastAPI（mock 路由 + OpenAPI）
    web/        Next.js（控制台 UI）
  packages/
    schemas/    共享 JSON Schema（Phase 0 冻结 + Phase 1 mock）
  docs/         PRD 与协议文档
```

## 组件映射（PRD 十层 → 当前骨架）

- **用户交互层**：`apps/web`
- **任务控制层（占位）**：`apps/api` 的 `/tasks` mock 路由（未来将迁移为真实状态机 + 队列）
- **Agent 编排层（占位）**：`apps/api` 的 `/agents` mock 路由
- **Skill 母线（占位）**：`/skills` mock 路由 + `packages/schemas` 协议草案
- **账号/凭证层（占位）**：`/accounts` mock 路由（不存真实凭证）
- **通知/Watchdog（占位）**：`/watchdog` mock 路由
- **平台记忆（占位）**：`/memory` mock 路由（仅展示候选/已存记忆的结构，不存真实向量/DB）

## TODO（phase>=2）

- TODO(phase>=2): 引入任务状态机与事件溯源（Task / Run / TaskEvent）
- TODO(phase>=2): 技能注册表与执行器（Skill Registry / Executor）
- TODO(phase>=2): 账号凭证安全存储（本地 Keychain/KMS）与权限策略
- TODO(phase>=3): 外部 Agent Adapter 协议落地（OpenClaw / Claude Code）
- TODO(phase>=4): 操控舱三模式交互（Commander/Pilot/Direct Agent）与 Timeline

