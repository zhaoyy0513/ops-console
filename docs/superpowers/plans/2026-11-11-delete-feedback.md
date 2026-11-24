# 删除操作全局反馈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一所有危险删除操作的成功/失败反馈为右下角 toast，并把 `CountdownConfirm` 的触发接口收口为 `onConfirm`。

**Architecture:** `Toaster` 固定 `bottom-right`；`CountdownConfirm` 只负责倒计时、pending 锁与失败保持弹窗，业务提示由调用方负责；成功 `message.success`，失败 `message.error` 后重抛；配置类删除补 error toast。

**Tech Stack:** Vue 3 + TypeScript + vue-sonner + Vitest + @vue/test-utils。

**Spec:** `docs/superpowers/specs/2026-11-11-delete-feedback-design.md`

---

## 文件结构

- Modify: `frontend/src/App.vue`（Toaster 位置）
- Modify: `frontend/src/components/CountdownConfirm.vue`（删除未使用的 emit）
- Modify: `frontend/src/components/CountdownConfirm.test.ts`（失败保持弹窗回归）
- Modify: `frontend/src/modules/redis/RedisView.vue`（`on-confirm` + 删除失败反馈）
- Modify: `frontend/src/modules/redis/RedisView.test.ts`（删除成功/失败链路）
- Modify: `frontend/src/modules/knowledge/KnowledgeView.vue`（失败重抛）
- Modify: `frontend/src/modules/page/PageView.vue`（失败重抛）
- Modify: `frontend/src/modules/mq/MqView.vue`（失败重抛）
- Modify: `frontend/src/modules/server/ServerView.vue`（失败重抛）
- Modify: `frontend/src/modules/ssh/SshView.vue`（失败 toast）
- Modify: `frontend/src/modules/sites/SiteResourcesDrawer.vue`（失败 toast）
- Modify: `frontend/src/layouts/MainLayout.vue`（build-stamp）

---

## Task 1: Toaster 位置与 CountdownConfirm 接口收口

**Files:**
- Modify: `frontend/src/App.vue:26`
- Modify: `frontend/src/components/CountdownConfirm.vue:24`
- Test: `frontend/src/components/CountdownConfirm.test.ts`

- [ ] **Step 1: 把 Toaster 改为右下角**

在 `frontend/src/App.vue` 中把：

```vue
<Toaster :theme="lightDark" position="top-center" rich-colors close-button />
```

改为：

```vue
<Toaster :theme="lightDark" position="bottom-right" rich-colors close-button />
```

- [ ] **Step 2: 删除 CountdownConfirm 未使用的 emit**

在 `frontend/src/components/CountdownConfirm.vue` 中删除这一行：

```ts
const emit = defineEmits<{ (e: 'confirm'): void }>()
```

保留 `onConfirm` prop 与现有 `onConfirmClick` 逻辑：成功关闭弹窗，失败复位 pending 并保持弹窗。

- [ ] **Step 3: 补失败保持弹窗回归测试**

在 `frontend/src/components/CountdownConfirm.test.ts` 的 `describe('CountdownConfirm', ...)` 中追加：

```ts
it('onConfirm 失败：保持弹窗并允许重试', async () => {
  const onConfirm = vi.fn().mockRejectedValueOnce(new Error('delete failed')).mockResolvedValue(undefined)
  await open(5, onConfirm)
  const modalConfirm = bodyButtons().find((b) => b.textContent?.trim() === 'Delete')!
  await vi.advanceTimersByTimeAsync(5000)
  modalConfirm.click()
  await vi.advanceTimersByTimeAsync(0)
  expect(document.body.querySelector('[role="alertdialog"]')).not.toBeNull()
  await vi.advanceTimersByTimeAsync(0)
  modalConfirm.click()
  await vi.advanceTimersByTimeAsync(0)
  expect(onConfirm).toHaveBeenCalledTimes(2)
})
```

- [ ] **Step 4: 运行组件测试**

Run: `cd frontend && npx vitest run src/components/CountdownConfirm.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.vue frontend/src/components/CountdownConfirm.vue frontend/src/components/CountdownConfirm.test.ts
git commit -m "refactor: 统一删除确认组件接口并固定右下角 toast"
```

---

## Task 2: Redis 删除链路与反馈

**Files:**
- Modify: `frontend/src/modules/redis/RedisView.vue:401-411`
- Modify: `frontend/src/modules/redis/RedisView.vue:828`
- Test: `frontend/src/modules/redis/RedisView.test.ts`

- [ ] **Step 1: 写失败测试**

在 `frontend/src/modules/redis/RedisView.test.ts` 末尾追加：

```ts
describe('RedisView delete feedback', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    stored = '{\n  "a": 1\n}'
    operateMock.mockClear()
    vi.mocked(message.error).mockClear()
    vi.mocked(message.success).mockClear()
  })

  afterEach(() => vi.useRealTimers())

  async function openDeleteConfirm() {
    btn('Delete')!.click()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(3000)
    const dialog = document.body.querySelector('[role="alertdialog"]')!
    return [...dialog.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Delete')!
  }

  it('删除成功：调用 operate(delete) + message.success', async () => {
    vi.useFakeTimers()
    const w = await boot()
    const confirmBtn = await openDeleteConfirm()
    confirmBtn.click()
    await flushPromises()
    expect(operateMock).toHaveBeenCalledWith('sz', 'r1', expect.objectContaining({ op: 'delete', key: 'jk' }))
    expect(message.success).toHaveBeenCalled()
    w.unmount()
  })

  it('删除失败：message.error 且确认框保留', async () => {
    operateMock.mockRejectedValueOnce(new Error('delete failed'))
    vi.useFakeTimers()
    const w = await boot()
    const confirmBtn = await openDeleteConfirm()
    confirmBtn.click()
    await flushPromises()
    expect(message.error).toHaveBeenCalledWith('delete failed')
    expect(document.body.querySelector('[role="alertdialog"]')).not.toBeNull()
    w.unmount()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/modules/redis/RedisView.test.ts`
Expected: FAIL，`operateMock` 未被调用或 `message.error` 未调用

- [ ] **Step 3: 修改 RedisView 触发接口与删除函数**

把 `frontend/src/modules/redis/RedisView.vue:828` 的：

```vue
<countdown-confirm :label="$t('common.delete')" :target="detail.key" :seconds="3" @confirm="deleteKey" />
```

改为：

```vue
<countdown-confirm :label="$t('common.delete')" :target="detail.key" :seconds="3" :on-confirm="deleteKey" />
```

把 `deleteKey` 改为：

```ts
async function deleteKey() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  try {
    await operate(siteStore.currentSiteId, instanceId.value, {
      op: 'delete', db: db.value, key: d.key,
    })
    message.success(t('redis.deleted', { key: d.key }))
    clearDetail()
    search(true)
    loadInfo()
  } catch (e) {
    message.error((e as Error).message)
    throw e
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/modules/redis/RedisView.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/modules/redis/RedisView.vue frontend/src/modules/redis/RedisView.test.ts
git commit -m "fix: Redis 删除反馈收口到 onConfirm 与全局 toast"
```

---

## Task 3: 其它 CountdownConfirm 调用方失败重抛

**Files:**
- Modify: `frontend/src/modules/knowledge/KnowledgeView.vue:84-90`
- Modify: `frontend/src/modules/page/PageView.vue:57-63`
- Modify: `frontend/src/modules/mq/MqView.vue:274-284`
- Modify: `frontend/src/modules/server/ServerView.vue:212-222`

- [ ] **Step 1: KnowledgeView 失败重抛**

把 `remove` 改为：

```ts
async function remove(d: KnowledgeDoc) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  try {
    await knowledgeApi.remove(siteId, d.id)
    message.success(t('knowledge.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
    throw e
  }
}
```

- [ ] **Step 2: PageView 失败重抛**

把 `remove` 改为：

```ts
async function remove(p: PageResource) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  try {
    await pageApi.remove(siteId, p.id)
    message.success(t('page.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
    throw e
  }
}
```

- [ ] **Step 3: MqView 失败重抛**

在 `emptyQueue` 的 `catch` 中，`messageBus.error` 之后补：

```ts
throw e
```

完整函数：

```ts
async function emptyQueue(q: QueueRow) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value || !q._mbean) return
  try {
    await mqApi.emptyQueue(siteId, instanceId.value, q._mbean, q.name)
    messageBus.success(`已清空 ${q.name} 的积压消息`)
    loadHeavy()
  } catch (e) {
    messageBus.error((e as Error).message)
    throw e
  }
}
```

- [ ] **Step 4: ServerView 失败重抛**

在 `killZombie` 的 `catch` 中，`messageApi.error` 之后补：

```ts
throw e
```

完整函数：

```ts
async function killZombie(z: ZombieGroup) {
  if (!siteStore.currentSiteId || !serverId.value) return
  try {
    await serverApi.killZombie(siteStore.currentSiteId, serverId.value, z.ppid, z.cmd)
    messageApi.success(t('server.zombieKilled'))
    await loadZombies()
    load(true) // 静默刷新卡片上的计数
  } catch (e) {
    messageApi.error((e as Error).message)
    throw e
  }
}
```

- [ ] **Step 5: 运行回归测试**

Run: `cd frontend && npx vitest run`
Expected: PASS（这些视图无独立删除测试，依赖 Task 1/2 的 CountdownConfirm 与 Redis 回归）

- [ ] **Step 6: 提交**

```bash
git add frontend/src/modules/knowledge/KnowledgeView.vue frontend/src/modules/page/PageView.vue frontend/src/modules/mq/MqView.vue frontend/src/modules/server/ServerView.vue
git commit -m "fix: 删除失败统一提示并保留确认框"
```

---

## Task 4: 配置类删除补错误反馈

**Files:**
- Modify: `frontend/src/modules/ssh/SshView.vue:235-240`
- Modify: `frontend/src/modules/sites/SiteResourcesDrawer.vue:162-172`

- [ ] **Step 1: SshView 删除补 catch**

把 `remove` 改为：

```ts
async function remove(item: SshScript) {
  if (!siteStore.currentSiteId) return
  try {
    await sshApi.remove(siteStore.currentSiteId, item.id)
    message.success(t('ssh.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}
```

- [ ] **Step 2: SiteResourcesDrawer 删除补 catch**

在 `remove` 的 `try/finally` 中补 `catch`：

```ts
async function remove(item: ResourceConfig) {
  if (deleting.value) return
  deleting.value = true
  try {
    await sitesApi.removeResource(siteId.value, activeType.value, item.id)
    message.success(t('sites.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    deleting.value = false
  }
}
```

- [ ] **Step 3: 确认 SitesView 已有反馈**

`frontend/src/modules/sites/SitesView.vue:130-141` 已有 `message.success` / `message.error`，不改动。

- [ ] **Step 4: 运行回归测试**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/modules/ssh/SshView.vue frontend/src/modules/sites/SiteResourcesDrawer.vue
git commit -m "fix: 配置类删除补全局错误反馈"
```

---

## Task 5: build-stamp 与全量验证

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue:202`

- [ ] **Step 1: 生成中国本地时间戳**

Run: `TZ=Asia/Shanghai date +%m%d-%H%M`
Expected: 输出类似 `1111-1630`

- [ ] **Step 2: 更新 build-stamp**

把 `frontend/src/layouts/MainLayout.vue:202` 的：

```vue
<span v-if="!collapsed" class="build-stamp font-mono">b1103-1918</span>
```

改为上一步输出对应的值，例如：

```vue
<span v-if="!collapsed" class="build-stamp font-mono">b1111-1630</span>
```

- [ ] **Step 3: 运行前端全量测试与构建**

Run: `cd frontend && npx vitest run`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS（允许现有 Vite chunk 体积警告）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/layouts/MainLayout.vue
git commit -m "chore: 更新前端 build-stamp"
```

---

## 完成门槛

- [ ] `cd frontend && npx vitest run` 全绿
- [ ] `cd frontend && npm run build` 成功
- [ ] `git status` 干净，仅保留与本任务无关的既有未跟踪文件
- [ ] 人工冒烟：Redis 删除成功/失败、MQ 清空失败、Server kill 失败，确认右下角 toast 且失败时确认框保留
