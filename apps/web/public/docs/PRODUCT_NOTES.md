# 产品与部署说明

本页概述当前 **Kāne / Kane Agent Platform** 在自建环境中的重要边界（面向运维与集成人员，非法律条款全文）。

## 能力边界（摘要）

- **本地优先**：默认可通过文件持久化运行；可选 PostgreSQL，Schema 为兼容层，可随版本演进。
- **身份与凭据**：按环境自行管理 API Key / Bridge 密钥；勿将 `.env` 提交到版本库。
- **外部智能体**：通过 Local Bridge、Webhook、CLI / handoff 等路径接入时，能力取决于你环境中的进程与网络，平台不替代你的安全评审。

## 生产使用前

在多租户或对公服务前，请自行补充身份、审计、备份与密钥管理策略。详见仓库内 `docs/DEPLOYMENT_*.md` 与 `docs/ARCHITECTURE.md`（若已随发行版提供）。
