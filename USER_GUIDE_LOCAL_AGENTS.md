# 本地多 Agent 操控台 — 用户指南（Beta）

面向**使用**章鱼平台（非仅阅读代码）的说明：各入口做什么、四类外部/本地 Agent 怎么接、怎么试跑与排障。技术细节与 API 列表另见 [`docs/EXTERNAL_AGENT_INTEGRATION.md`](docs/EXTERNAL_AGENT_INTEGRATION.md)、[`docs/API_ROUTE_INVENTORY.md`](docs/API_ROUTE_INVENTORY.md)。Beta 边界见 [`docs/BETA_LIMITATIONS.md`](docs/BETA_LIMITATIONS.md)。

---

## 1. 哪个入口干什么

| 路径 | 用来做什么 | 您能做什么 | 归类 |
|------|------------|------------|------|
| **`/local-bridge`** | 看 **Local Bridge** 是否连上、地址是否正确 | 查看状态、一键 **探测（probe）**、看错误提示 | **试跑 / 排障**（Bridge 侧） |
| **`/agents/add`** | **注册新 Agent** 到平台 | 选模板、填最小配置、提交；可选登记到 Bridge | **添加 Agent** |
| **`/agent-fleet`** | **总览**已注册 Agent | 浏览、筛选、点进某个 Agent | **查看状态**（集群视角） |
| **`/agent-fleet/[id]`** | 单个 Agent 的 **详情与配置** | 看接入方式/通道/控制深度；可编辑字段会 **保存（PATCH）**；**测试连接 / 试跑** | **配置 Agent** + **试跑** |
| **`/cockpit`** | 操控舱：从对话式入口 **发起工作** | 创建任务、走分配/运行（与任务流联动） | **发任务**（入口之一） |
| **`/tasks`** | **任务列表与创建** | 新建任务、查看状态、点进详情看时间线与输出 | **发任务** + **查看状态** |
| **`/settings`** | 全局设置：API Profile、通知摘要等 | 配置模型与密钥、跳到通知全页 | **配置环境**（偏账户/模型，非单 Agent 适配器） |
| **`/notifications`** | 通知频道列表与管理 | 查看渠道、启用/禁用（Beta 能力边界内） | **查看状态**（通知侧） |

**记忆口诀**：加人去 **`/agents/add`**，编队看 **`/agent-fleet`**，改一个人去 **`/agent-fleet/[id]`**，Bridge 不通先 **`/local-bridge`**，干活主 **`/tasks`** 或 **`/cockpit`**。

---

## 2. OpenClaw（开源 AI Agent）怎么接

- **当前接入方式**：平台 → API → **Local Bridge** → 若配置了 **`OPENCLAW_WEBHOOK_URL`** 则 **HTTP Webhook** 调您的 OpenClaw；否则 Bridge 会生成 **handoff** 说明，需人工在 OpenClaw 侧处理，完成后可走 **callback** 结束等待态（与任务策略有关）。
- **您需要准备**：可运行的 Bridge（本机或同网络）、OpenClaw 可接收 Webhook 的 URL（若走自动 POST）、以及平台与 Bridge 一致的环境变量（见根目录 `.env.example` 与 Bridge README）。
- **在平台里从哪里添加**：**`/agents/add`** → 选择 OpenClaw 相关模板 → 填 **Agent ID**、适配器/登记信息 → 提交。
- **要配哪些字段**：至少 **唯一 Agent ID**；其余按表单与页面上的「诚实说明」— Webhook 依赖 Bridge 环境，不是单靠浏览器里一行字就能替代。
- **怎么测试是否接通**：保存后打开 **`/agent-fleet/[id]`** → 使用 **测试连接 / 试跑**；成功则任务状态会推进并能看到结果摘要；若只显示等待/handoff，按页面提示检查 Webhook 与 callback。
- **目前能做到什么**：在 Beta 内完成 **登记、试跑、状态观测**；Webhook 路径在环境齐时可 **自动出队**。
- **当前限制**：未配置 Webhook 时 **不会**假装已全自动；多租户隔离、生产级安全与 SLA 不在 Beta 承诺内。

---

## 3. Cursor（闭源 AI Agent）怎么接

- **为什么不算「完整内嵌」**：Cursor 为 **闭源 IDE**，**没有**稳定、公开的「远程无头执行任务」API 供本平台像内置插件一样完全遥控。
- **当前接入方式**：**Assisted** — Bridge 侧以 **handoff**（可读文件/说明）+ 您在 Cursor 里人工执行 + **`POST /integrations/bridge/complete` 回调** 结束任务等待。
- **您需要做什么**：安装 Cursor、能打开 handoff 指向的工作内容；按文档完成回调（或在本机脚本中代劳）。
- **在平台里从哪里配置**：**`/agents/add`** 添加；**`/agent-fleet/[id]`** 查看与 PATCH 可编辑项。
- **能做哪些事**：统一 **登记、派单、看状态、试跑（会进入 handoff/等待）**、在回调后 **闭环**。
- **哪些事做不到**：不能保证 **无人值守** 全自动驱动 Cursor UI；不能保证官方长期兼容。
- **闭源 / 无正式接口的表述**：本平台提供的是 **编排与观测 + handoff 辅助**，不是 Cursor 官方嵌入式集成。

---

## 4. Claude Code（闭源 AI Agent）怎么接

- **当前接入方式**：同样经 **Local Bridge**。若本机存在 **`claude` CLI**，Bridge 可尝试 **CLI 非交互**路径；否则与 Cursor 类似走 **handoff**，依赖人工或后续 callback。
- **CLI / handoff / bridge 的含义**：**Bridge** 是跑在您机器上的 HTTP 小服务；**CLI** 指本机调用 `claude` 命令；**handoff** 指把上下文写到文件/说明，供您在 Claude Code 里继续；**callback** 指外部干完后通知平台 API。
- **您怎么配**：**`/agents/add`** 选 Claude Code 模板，填 ID 等；Bridge 与 API 的 URL/密钥按 `.env.example`。
- **您怎么试跑**：**`/agent-fleet/[id]`** 的测试区；观察输出是 CLI 成功、还是进入 handoff/waiting。
- **当前限制**：无 CLI 时 **不会**宣称已执行成功；商业产品行为以厂商为准。

---

## 5. 其他本地脚本 Agent（local_script）怎么接

- **为什么更适合 Embedded / Native**：命令在 **Bridge 所在主机**上执行，不依赖第三方闭源 IDE API，路径短、可重复、易自动化（需注意 **命令注入** 与权限，由您自控）。
- **您怎么添加**：**`/agents/add`** → 选 **本地脚本 / shell** 类模板 → 配置 **`shell_command`** 等（以表单为准）。
- **您怎么试跑**：详情页 **测试**；成功时 Run/任务输出里可见 **stdout/stderr** 摘要（以实际 UI 为准）。
- **怎么知道成功或失败**：任务状态 **succeeded/failed**、时间线事件与试跑结果区文案；失败时会有 **原因或建议**（handoff/策略阻塞时也会标明）。

---

## 相关文档

- 能力矩阵（工程师向）：[`AGENT_INTEGRATION_MATRIX.md`](AGENT_INTEGRATION_MATRIX.md)  
- 阶段进度与差距（是否保留见 [`DOC_CLEANUP_LOG.md`](DOC_CLEANUP_LOG.md)）：[`LOCAL_AGENT_CONTROL_PLANE_PROGRESS.md`](LOCAL_AGENT_CONTROL_PLANE_PROGRESS.md)、[`LOCAL_AGENT_CONTROL_PLANE_GAP_LIST.md`](LOCAL_AGENT_CONTROL_PLANE_GAP_LIST.md)  
- 验证与 E2E 证据：[`FINAL_VALIDATION.md`](FINAL_VALIDATION.md)
