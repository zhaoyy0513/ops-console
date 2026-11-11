# 删除操作全局反馈设计

日期：2026-11-11　分支：feature/v2.0.0

## 背景与目标

当前危险操作统一走 `CountdownConfirm` 倒计时确认，但删除后的成功/失败反馈散落在各 view：

- 成功提示有的是页面内联横幅，有的是一句话 toast，位置和样式不统一。
- 失败提示依赖调用方各自 `catch`，部分删除失败时确认框已关，用户不知道原因。
- `Toaster` 固定在 `App.vue`，源码位置是 `top-center`，与顶部 sticky header 争视觉；实测提示位置也与源码不一致。

本次设计目标：

1. 所有删除/清空/终止类危险操作，确认后统一从**右下角 toast** 给出成功或失败反馈。
2. 成功：关闭确认框，提示「已删除 / 已清空 / 已终止 + 目标名」，并刷新数据。
3. 失败：确认框保留，右下角 error toast 显示后端原因，允许重试。
4. 不引入 alert 横幅、undo、全局删除状态机，保持最小改动。

不在范围：`compose.yaml` 服务命名（有意设计，不改）、非删除类提示、后端 oplog、删除撤销。

## 现状核对

- 全局 toast 入口已是 `frontend/src/lib/message.ts`，底层为 `vue-sonner`。
- `Toaster` 挂载在 `frontend/src/App.vue`，当前 `position="top-center"`。
- `CountdownConfirm` 声明了 `confirm` emit，但组件内未调用；实际成功回调是 `onConfirm` prop。
- Redis 删除处写的是 `@confirm="deleteKey"`，与其它页面的 `:on-confirm` 不一致；实测可删，说明运行链路存在隐式行为，本次统一为显式 `onConfirm`。
- 多数删除调用方已有 `message.success`，但失败路径不统一，部分未 `catch` 或未重抛。

## 设计决策

### 1. 反馈位置：右下角 toast

`Toaster` 改为 `position="bottom-right"`。理由：

- 不遮挡顶部 header 的站点切换、操作日志、语言按钮。
- 符合后台系统通知习惯，成功/失败同一通道，学习成本低。
- `vue-sonner` 默认 z-index 远高于 modal 遮罩，无需额外处理层级。

不采用顶部 alert 横幅：成功提示会变重，且需要额外组件与状态管理，噪音大于收益。

### 2. 组件职责：CountdownConfirm 只管确认与锁

`CountdownConfirm` 只负责：

- 倒计时解锁确认按钮。
- 执行中 pending 锁，防连点。
- 成功后关闭确认框。
- 失败后保持确认框并复位 pending。

业务提示由调用方负责：成功 `message.success(...)`，失败 `message.error(...)` 后重抛，让确认框保持打开。组件不吞错误、不重复提示。

### 3. 统一触发接口

- 删除 `CountdownConfirm` 中未使用的 `confirm` emit。
- 只保留 `onConfirm?: () => Promise<unknown> | void`。
- Redis 从 `@confirm="deleteKey"` 改为 `:on-confirm="deleteKey"`。
- 其它页面继续保持 `:on-confirm`，不改变已实测可用的行为。

## 改动清单

### 前端全局

- `frontend/src/App.vue`
  - `Toaster` 的 `position` 改为 `bottom-right`。
  - 保留 `rich-colors`、`close-button`、主题联动。

### 确认组件

- `frontend/src/components/CountdownConfirm.vue`
  - 删除 `defineEmits<{ (e: 'confirm'): void }>()`。
  - 保留 `onConfirm` prop 与 pending/失败保持弹窗逻辑。
  - 注释明确：调用方负责业务 toast；失败需重抛以保留确认框。

### 危险资源操作

- `frontend/src/modules/redis/RedisView.vue`
  - `@confirm="deleteKey"` → `:on-confirm="deleteKey"`。
  - `deleteKey` 补 `try/catch`：成功 `message.success(t('redis.deleted', { key }))` 后刷新；失败 `message.error(...)` 并重抛。
- `frontend/src/modules/knowledge/KnowledgeView.vue`
  - 统一 `remove`：成功 toast + 刷新；失败 toast + 重抛。
- `frontend/src/modules/page/PageView.vue`
  - 统一 `remove`：成功 toast + 刷新；失败 toast + 重抛。
- `frontend/src/modules/logs/LogsView.vue`
  - 统一 `removeDraft`：成功 toast + 刷新；失败 toast + 重抛。
- `frontend/src/modules/mq/MqView.vue`
  - `emptyQueue` 统一成功/失败 toast，失败重抛。
- `frontend/src/modules/server/ServerView.vue`
  - `killZombie` 统一成功/失败 toast，失败重抛。

### 配置类删除

- 站点、资源、SSH 脚本删除当前走普通 `AlertDialog`，本次只补 success/error toast，不改确认方式：
  - `frontend/src/modules/sites/SitesView.vue`
  - `frontend/src/modules/sites/SiteResourcesDrawer.vue`
  - `frontend/src/modules/sites/ResourceEditModal.vue`
  - `frontend/src/modules/ssh/SshView.vue`
- 成功提示复用各模块现有文案；失败提示统一取后端错误 message。

### 收尾

- `frontend/src/layouts/MainLayout.vue`
  - 按项目规则更新 build-stamp（`bMMDD-HHMM`，中国本地时间）。

## 数据流

```text
点击删除
  → CountdownConfirm 打开，3s 倒计时
  → 点击确认
  → onConfirm 执行后端删除
      ├─ 成功：message.success（右下角 toast）→ 关闭确认框 → 刷新列表
      └─ 失败：message.error（右下角 toast）→ 重抛 → 确认框保留，pending 复位
```

## 错误处理

- 后端错误经 axios 拦截器转为可读 message，直接进 error toast。
- 删除失败不关闭确认框，避免用户误以为成功。
- 轮询类失败沿用现有“成功→失败边缘提示一次”策略，不改成全局删除反馈。
- 网络中断时 toast 显示请求失败，确认框保持打开。

## 测试

- `frontend/src/components/CountdownConfirm.test.ts`
  - 成功：`onConfirm` resolve 后关闭确认框。
  - 失败：`onConfirm` reject 后确认框保留、pending 复位、可重试。
  - 确认不再依赖未使用的 `confirm` emit。
- `frontend/src/modules/redis/RedisView.test.ts`
  - 删除成功：调用 `operate`，触发 `message.success`，清空详情并刷新。
  - 删除失败：触发 `message.error`，确认框不关闭。
- 完成门槛：`cd frontend && npx vitest run` 与 `npm run build` 双绿。
