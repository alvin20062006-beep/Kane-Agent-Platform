# EXTERNAL_AGENT_INTEGRATION（外部 Agent：诚实说明）

母本规格：`docs/PRD.md` §11。

## 集成矩阵（Beta）

| Agent | 路径 | 何时算「真实可用」 |
|--------|------|---------------------|
| **Octopus builtin** | API 内置 `execute_builtin_octopus` | 始终同步可用（无外部 LLM） |
| **Claude Code** | API → Bridge `POST /v1/execute` → `claude -p` 或 handoff 文件 | 机器上 `claude` 在 PATH 且非交互可用时，CLI 路径为真；否则为 **handoff + callback** |
| **OpenClaw** | Bridge `OPENCLAW_WEBHOOK_URL` HTTP POST 或 handoff | Webhook 返回 2xx 且对端真实处理时为真；否则为 handoff |
| **Cursor** | Bridge 写 `cursor_handoff_file`；可选探测 `cursor --version` | **不宣称**无头全自动；以 handoff + 人工在 Cursor 执行 + callback 为主 |

## 端到端（推荐演示）

1. 启动 API + Bridge + Web  
2. Cockpit 选择 `claude_code_external`，运行任务  
3. **A 路径**：已安装 Claude CLI → 同步输出  
4. **B 路径**：未安装 → 任务进入 `waiting_approval`，按 handoff 中说明调用：

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

## 安全

Beta 可选 `OCTOPUS_BRIDGE_SHARED_SECRET`；**非**生产级零信任。
