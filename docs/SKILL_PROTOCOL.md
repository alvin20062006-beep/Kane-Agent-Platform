# SKILL_PROTOCOL（技能协议与现状）

本文件描述技能的 **目标字段形状** 与 **当前实现关系**：仓库中已有 **技能注册表持久化** 与 **`POST /skills/{skill_id}/execute`** 执行路径（见 `apps/api/app/services/skills_executor.py`），并非「仅协议草案、无执行器」。

## Skill 定义（目标字段）

每个 Skill 至少包含（与 OpenAPI / 种子数据对齐）：

- `skill_id`、`name`、`version`、`description`、`category`
- `input_schema` / `output_schema`（JSON Schema 引用或内联）
- `required_credentials`（引用凭证 id；敏感值 write-only）
- `risk_level`、`default_execution_policy`、`supported_agents`
- `timeout_seconds`、`retry_policy` 等

## 当前实现要点

- 列表 API 经 `skill_visibility` 过滤用户可见项；部分内部/示例技能可不展示。
- **执行**：通过 API 路由委托 `execute_skill`，可能产生任务事件与 run 日志；具名 skill 行为以代码为准（如 HTTP、内置 demo 等）。
- **发布 / 更新**：`publish`、`PATCH`、`DELETE` 等路由存在；能力与权限边界以控制面配置为准。

## 尚未宣称的能力

- 企业级技能市场签名、供应链审计、跨租户隔离。
- 与托管向量库的深度耦合（除非部署侧自行扩展）。

## 延伸阅读

- `docs/API.md` — `/skills` 相关路由
- `packages/schemas/json/skill.schema.json`
