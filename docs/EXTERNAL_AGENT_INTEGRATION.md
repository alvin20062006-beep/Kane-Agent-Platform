# EXTERNAL_AGENT_INTEGRATION（外部 Agent：诚实说明）

以下为与 **当前仓库代码**（`apps/api`、`apps/local-bridge`）一致的集成说明。

## 集成矩阵

| Agent / 适配器 | 路径 | 何时算「自动化可用」 |
|----------------|------|----------------------|
| **Octopus 内置** | API 内置执行器（如 Kanaloa 路径） | 不依赖 Bridge；同步执行策略由 worker 调度 |
| **Claude Code** | API → Bridge `POST /v1/execute`，`adapter_id=claude_code` | 本机存在 `claude` 可执行文件且 `claude -p` 在非交互场景可用时，返回 CLI 输出；否则生成 **handoff 文件** + 需 `bridge/complete` |
| **OpenClaw HTTP** | Bridge：`OPENCLAW_WEBHOOK_URL` 已配置时 POST JSON | Webhook 返回 2xx 且对端真实处理；未配置则 **handoff 文件** |
| **Cursor** | Bridge：`adapter_id=cursor_cli`，写 handoff | **不宣称**无头全自动；以 handoff + 人工在 Cursor 内执行 + 回调为主 |
| **local_script** | Bridge 本机 `subprocess` | 需在 Agent `control_plane` 中配置 `shell_command` 等；**仅在受信环境**启用 |

## 异步完成（回调 API）

`POST {OCTOPUS_API_PUBLIC_URL}/integrations/bridge/complete`

```json
{
  "task_id": "...",
  "run_id": "...",
  "status": "succeeded",
  "output": "paste result",
  "error": null,
  "integration_path": "manual_claude_code"
}
```

若配置 `OCTOPUS_BRIDGE_SHARED_SECRET`，请求需带头 `X-Octopus-Bridge-Key`。

## 安全

可选共享密钥 **`OCTOPUS_BRIDGE_SHARED_SECRET`** 用于减轻误连，**不是**零信任或 mTLS 方案；Bridge 暴露的本机执行面应仅放在内网或本机。
