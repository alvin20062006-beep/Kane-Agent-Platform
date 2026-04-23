# API（Phase 1 foundation）

本阶段 API 目标：提供**可运行**的 FastAPI 服务，包含健康检查与资源列表端点，返回明确标注的 **MOCK 数据**。

Base URL（本地开发）：

- `http://127.0.0.1:8000`

OpenAPI：

- `http://127.0.0.1:8000/docs`

## Endpoints

### GET `/health`

用于健康检查（真实）。

### GET `/agents`

返回 Agent Fleet 列表（MOCK）。

### GET `/tasks`

返回任务列表（MOCK）。

### GET `/skills`

返回技能列表（MOCK）。

### GET `/accounts`

返回账号列表（MOCK，**不含真实凭证**）。

### GET `/memory`

返回记忆条目列表（MOCK）。

### GET `/watchdog`

返回 watchdog 状态与事件（MOCK）。

## TODO（phase>=2）

- TODO(phase>=2): 为每个资源增加创建/更新/删除与审计日志
- TODO(phase>=2): 引入任务状态机与事件流（TaskEvent / RunLog）
- TODO(phase>=3): SSE/WebSocket 推流（任务 timeline / agent 输出）

