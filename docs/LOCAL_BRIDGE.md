# LOCAL_BRIDGE（占位 / 不在本阶段实现）

Octopus Local Bridge 用于连接本地环境（Claude Code、本地脚本、浏览器 session、MCP、本地文件等）。

本仓库 Phase 0 + Phase 1 foundation **不实现** Local Bridge 服务，仅冻结目标能力与接口方向。

## 目标能力（后续）

- Agent 注册与心跳上报
- 接收任务、回传结果
- 本地技能执行（受策略约束）
- 本地敏感凭证存储（Keychain/KMS）
- 本地日志回传

## TODO（phase>=3）

- TODO(phase>=3): `apps/local-bridge` 服务骨架
- TODO(phase>=3): 与 `apps/api` 的安全通信（mTLS/签名）

