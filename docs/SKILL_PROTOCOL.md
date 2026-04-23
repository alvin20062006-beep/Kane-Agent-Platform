# SKILL_PROTOCOL（草案 / Phase 0 冻结接口形状）

本阶段仅冻结协议形状与字段命名，不实现真实 Skill 执行器。

## Skill 定义（目标）

每个 Skill 至少包含：

- `skill_id`
- `name`
- `version`
- `description`
- `category`
- `input_schema`（JSON Schema 引用）
- `output_schema`（JSON Schema 引用）
- `required_credentials`（数组；本阶段仅占位）
- `risk_level`（low/medium/high）
- `default_execution_policy`（auto/notify/confirm）
- `supported_agents`（数组；本阶段仅占位）
- `timeout_seconds`
- `retry_policy`（次数/退避；本阶段仅占位）

## TODO（phase>=2）

- TODO(phase>=2): Skill Registry（注册、版本、启停、审计）
- TODO(phase>=2): Skill Executor（运行、超时、重试、日志）
- TODO(phase>=2): 账号/凭证绑定与最小权限授权

