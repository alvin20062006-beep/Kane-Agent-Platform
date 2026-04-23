# MOBILE_ENTRY（Phase 5 占位）

本仓库 Phase 5 的目标是提供“移动端入口体验”的占位验证，不发布真实移动 App。

## 当前实现

- Web 路由：`/mobile`
  - 响应式布局
  - 快速动作入口（跳转到 cockpit/tasks/agent-fleet/watchdog）
  - 审批队列占位（按钮禁用）

## 明确不做

- App Store/安装包发布
- FCM/APNs Push
- OAuth 登录（本仓库整体暂不实现）

## TODO（phase>=5）

- TODO(phase>=5): 真实移动端（React Native/Expo）工程初始化
- TODO(phase>=5): 审批与通知的安全通道与权限模型

