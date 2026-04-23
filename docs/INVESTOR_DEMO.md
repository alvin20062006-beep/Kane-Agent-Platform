# INVESTOR_DEMO（投资人演示脚本）

## 叙事（30–60 秒）

章鱼平台是 **多 Agent 控制面 + 任务总账 + 操控舱**：同一任务流可接内置执行体与外部工程工具链（Claude Code / OpenClaw / Cursor 工作流），并且**诚实标注**自动化边界。

## 演示步骤（本地）

1. 三窗格：API docs、Web `/cockpit`、终端 Local Bridge  
2. Cockpit：创建任务 → 分配 **Octopus builtin** → 运行：展示 **Timeline + run_logs**  
3. 切换 **Claude Code** Agent：运行 → 展示 **CLI 输出或 handoff + waiting_approval**  
4. 打开 `GET /metrics` 与 `GET /watchdog`：展示运行态  
5. 强调：`docs/BETA_LIMITATIONS.md` 与 **不做假集成声明**

## 可讲清楚的护城河（Beta 可见部分）

- 任务事件溯源（events / runs / logs）与可插拔 Adapter
- Local Bridge 将“桌面/CLI 现实”接回平台总账
