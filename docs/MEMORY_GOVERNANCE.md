# MEMORY_GOVERNANCE（草案 / Phase 0 冻结接口形状）

本阶段只定义“平台级记忆总账”的治理规则与字段形状，API 仅返回 mock 数据，不做真实存储与向量检索。

## 核心原则

- 平台记忆是**总账**，外部 Agent/内置 Agent 记忆是**分账**
- 记忆必须有：来源、置信度、可过期性、可删除性、权限边界
- 外部 Agent **不能默认读取**所有平台记忆，必须受规则约束
- 明文密码/token **不应**进入长期记忆

## 记忆生命周期（目标）

1) **候选记忆**（pending）  
2) 用户审批：approved / rejected  
3) 进入长期记忆（memories）或过期/删除  

## TODO（phase>=6）

- TODO(phase>=6): 候选记忆审批 UI
- TODO(phase>=6): 记忆权限规则（MemoryAccessRule）与审计
- TODO(phase>=6): 过期策略与“敏感记忆保护”

