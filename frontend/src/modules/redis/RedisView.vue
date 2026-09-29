<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NSkeleton,
  NTag,
  NTooltip,
  NTree,
  useMessage,
  type TreeOption,
} from 'naive-ui'
import { parser as jsonParser } from '@lezer/json'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import TabHelp from '../../components/TabHelp.vue'
import DiffJsonEditor from '../../components/DiffJsonEditor.vue'
import { useSiteStore } from '../../stores/site'
import {
  getKey,
  getInfo,
  listKeys,
  operate,
  type KeyDetail,
  type KeyItem,
  type RedisInfo,
} from './api'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()

// ---------- 实例 / DB / 搜索 ----------
const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const db = ref(0)
const pattern = ref('')

const keys = ref<KeyItem[]>([])
const cursor = ref(0)
const loading = ref(false)
const info = ref<RedisInfo | null>(null)

/** DB 下拉：label 'DB5'（选中框显示），render-label 在数字后加灰色 [key 数] */
const DB_OPTIONS = computed(() =>
  Array.from({ length: 16 }, (_, i) => ({
    label: `DB${i}`,
    value: i,
  })),
)

function renderDbLabel(option: { label?: string; value?: number }) {
  const n = info.value?.db_sizes?.[option.value as number]
  return h('span', { class: 'db-option' }, [
    h('span', null, `DB${option.value}`),
    n != null ? h('span', { class: 'db-count' }, `  [${n}]`) : null,
  ])
}

async function loadInstances() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'redis')
    instances.value = list.map((r) => ({ label: r.name, value: r.id }))
    if (!instanceId.value || !list.some((r) => r.id === instanceId.value)) {
      instanceId.value = list[0]?.id ?? null
    }
  } catch (e) {
    message.error((e as Error).message)
  }
}

/** silent：5s 轮询用，不闪 loading 骨架/转圈（手动入口仍走 loading）；
 *  count：单页拉取量（轮询传当前已加载数，"加载更多"的成果不因刷新收缩） */
async function search(reset = true, silent = false, count = 100) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  if (!silent) loading.value = true
  try {
    const page = await listKeys(siteStore.currentSiteId, instanceId.value, {
      db: db.value,
      pattern: pattern.value.trim(),
      cursor: reset ? 0 : cursor.value,
      count,
    })
    keys.value = reset ? page.keys : [...keys.value, ...page.keys]
    cursor.value = page.cursor
  } catch (e) {
    if (!silent) message.error((e as Error).message)
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadInfo() {
  if (!siteStore.currentSiteId || !instanceId.value) return
  try {
    info.value = await getInfo(siteStore.currentSiteId, instanceId.value, db.value)
  } catch {
    info.value = null
  }
}

function refreshDb() {
  search(true)
  loadInfo()
}

onMounted(() => {
  loadInstances()
  startTimers()
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  stopTimers()
  document.removeEventListener('visibilitychange', onVisibility)
})
watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  keys.value = []
  info.value = null
  clearDetail()
  loadInstances()
})
watch(instanceId, () => {
  clearDetail()
  refreshDb()
})

// ---------- 树（':' 分层折叠 + 自然排序；点击整行任意位置展开/折叠） ----------

interface TreeDir { key: string; label: string; dir: true; children: TreeNode[]; count: number }
interface TreeLeaf { key: string; label: string; dir: false; item: KeyItem }
type TreeNode = TreeDir | TreeLeaf

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
const expandedKeys = ref<string[]>([])

function countLeaves(n: TreeNode): number {
  return n.dir ? n.children.reduce((s, c) => s + countLeaves(c), 0) : 1
}

function sortTree(nodes: TreeNode[]): TreeNode[] {
  nodes.sort((a, b) => collator.compare(a.label, b.label))
  for (const n of nodes) if (n.dir) sortTree(n.children)
  return nodes
}

function buildTree(items: KeyItem[]): TreeNode[] {
  const dirs = new Map<string, TreeDir>()
  const roots: TreeNode[] = []
  for (const item of items) {
    const parts = item.key.split(':')
    let container = roots
    let prefix = ''
    parts.forEach((part, i) => {
      prefix = prefix ? `${prefix}:${part}` : part
      if (i === parts.length - 1) {
        container.push({ key: `L:${item.key}`, label: item.key, dir: false, item })
      } else {
        let d = dirs.get(prefix)
        if (!d) {
          d = { key: `D:${prefix}`, label: part, dir: true, children: [], count: 0 }
          dirs.set(prefix, d)
          container.push(d)
        }
        container = d.children
      }
    })
  }
  for (const d of dirs.values()) d.count = countLeaves(d)
  return sortTree(roots)
}

const treeData = computed(() => buildTree(keys.value) as unknown as TreeOption[])

function toggleDir(node: TreeDir) {
  expandedKeys.value = expandedKeys.value.includes(node.key)
    ? expandedKeys.value.filter((k) => k !== node.key)
    : [...expandedKeys.value, node.key]
}

/** 展开全部 / 收起全部：目录键从当前树实时求值（刷新重建后仍有效） */
function expandAll() {
  const out: string[] = []
  const walk = (nodes: TreeNode[]) => {
    for (const n of nodes) if (n.dir) {
      out.push(n.key)
      walk(n.children)
    }
  }
  walk(treeData.value as unknown as TreeNode[])
  expandedKeys.value = out
}
function collapseAll() {
  expandedKeys.value = []
}

function renderLabel({ option }: { option: TreeOption }) {
  const node = option as unknown as TreeNode
  if (node.dir) {
    // label 铺满整行并接管点击（select 事件对已选中项不再触发，会导致"点两下"）
    return h('span', {
      class: 'tree-label tree-dir-row',
      onClick: (e: Event) => {
        e.stopPropagation()
        toggleDir(node)
      },
    }, [
      h('span', null, node.label),
      h('span', { class: 'tree-count' }, ` (${node.count})`),
    ])
  }
  return h('span', { class: 'tree-label mono', title: node.item.key }, node.label)
}

function onTreeSelect(_keys: Array<string>, options: Array<unknown>) {
  const option = options?.[0] as unknown as TreeNode | null
  if (option && !option.dir) selectKey(option.item)
}

// ---------- 详情（左树右值；Text/Json 自动感知 + CodeMirror 直接编辑） ----------
const selected = ref<KeyItem | null>(null)
const detail = ref<KeyDetail | null>(null)
const detailLoading = ref(false)
const format = ref<'text' | 'json'>('text')
const editText = ref('')
/** 打开 key 时从 Redis 装载的原始值（diff 基线，不随编辑变化） */
const originalText = ref('')
const editTtl = ref<number | null>(null)
/** 装载/应用 TTL 后的基线：轮询刷新用它判断"用户是否改过 TTL 输入"（未改才允许后端值回显） */
const editTtlLoaded = ref<number | null>(null)
const saving = ref(false)
const confirmShow = ref(false)

function isJson(s: string): boolean {
  const t = s.trim()
  if (!(t.startsWith('{') || t.startsWith('['))) return false
  try {
    JSON.parse(t)
    return true
  } catch {
    return false
  }
}

/** JSON 语法错误定位：lezer 解析拿错误节点位置 -> 行/列 + 附近文本（补全字段名，
 *  V8 原生错误如 'Unexpected token ",", ..."_seconds":...' 常被截断看不清字段）。
 *  注意 lezer 是容错解析器，parse 永不抛错——错误只能从 error 节点拿 */
function locateJsonError(text: string): string {
  let pos: number | null = null
  jsonParser.parse(text).iterate({
    enter: (n) => {
      if (n.type.isError && pos === null) pos = n.from
    },
  })
  if (pos === null) return t('redis.jsonSyntax')
  const before = text.slice(0, pos)
  const line = before.split('\n').length
  const col = pos - before.lastIndexOf('\n')
  const near = text.slice(Math.max(0, pos - 50), Math.min(text.length, pos + 50)).trim()
  return t('redis.jsonErrorAt', { line, col, near })
}

/** 打开的 key 装载时内容是否为 JSON（不随视图切换/编辑变化）：
 *  JSON 值的 key 在 Text 视图改坏也必须拦下（曾因 jsonInvalid 只看 format 而静默写坏） */
const loadedAsJson = ref(false)

const jsonInvalid = computed(() => {
  if (format.value !== 'json' && !loadedAsJson.value) return null
  try {
    JSON.parse(editText.value)
    return null
  } catch {
    return locateJsonError(editText.value)
  }
})

function toEditText(d: KeyDetail): string {
  const v = d.value
  if (d.type === 'string') return String(v ?? '')
  return JSON.stringify(v ?? null, null, 2)
}

/** 打开 key：自动感知格式；JSON 内容格式化后进编辑器（可直接编辑、实时校验） */
async function selectKey(k: KeyItem) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  selected.value = k
  detailLoading.value = true
  try {
    const d = await getKey(siteStore.currentSiteId, instanceId.value, db.value, k.key)
    if (d.type === 'none') {
      // key 已被删除/过期：明确提示并清空右侧（不再让用户对着旧值操作），列表同步去掉该 key
      message.error(t('redis.keyGone', { key: k.key }))
      clearDetail()
      search(true)
      return
    }
    detail.value = d
    const raw = toEditText(d)
    loadedAsJson.value = isJson(raw)
    format.value = loadedAsJson.value ? 'json' : 'text'
    editText.value = format.value === 'json'
      ? JSON.stringify(JSON.parse(raw), null, 2)
      : raw
    originalText.value = editText.value
    editTtl.value = d.ttl > 0 ? d.ttl : null
    editTtlLoaded.value = editTtl.value
  } catch (e) {
    // 连接失败等瞬断：提示并清空（旧值不可再操作）
    message.error((e as Error).message)
    clearDetail()
  } finally {
    detailLoading.value = false
  }
}

function clearDetail() {
  selected.value = null
  detail.value = null
}

function refreshValue() {
  if (selected.value) selectKey(selected.value)
}

function switchFormat(v: string) {
  const next = v as 'text' | 'json'
  if (next === 'json') {
    // 进 Json 视图：格式化展示（CodeMirror 高亮 + 实时校验，可直接编辑）
    if (isJson(editText.value)) {
      const pretty = JSON.stringify(JSON.parse(editText.value), null, 2)
      // 未编辑过的内容格式化时，diff 基线同步格式化（否则整篇都算变更）
      if (editText.value === originalText.value) originalText.value = pretty
      editText.value = pretty
      format.value = 'json'
    } else {
      message.warning(t('redis.notJson'))
    }
  } else {
    format.value = 'text'
  }
}

/** 保存前校验（两个入口共用）：jsonInvalid 覆盖 Json 视图语法错误 + JSON 值的 key
 *  在 Text 视图被改坏（loadedAsJson 基线，见 computed）——一律拦截 */
function validateBeforeSave(): boolean {
  if (jsonInvalid.value) {
    message.error(t('redis.jsonInvalidSave', { reason: jsonInvalid.value }))
    shakeBanner()
    return false
  }
  return true
}

/** 保存按钮入口：必须先校验再开确认弹窗（不能反过来在弹窗里报错）——
 *  message 挂在 App 内的 provider 下（不 teleport），弹窗遮罩 z-index 更高，会把 toast 盖住 */
function openSaveConfirm() {
  if (validateBeforeSave()) confirmShow.value = true
}

// 错误横幅抖动：让"没保存成功"除 toast 外还有就地视觉反馈
const bannerShake = ref(false)
let shakeTimer: number | undefined
function shakeBanner() {
  bannerShake.value = true
  clearTimeout(shakeTimer)
  shakeTimer = window.setTimeout(() => (bannerShake.value = false), 400)
}

async function saveValue() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  if (!validateBeforeSave()) return
  // 非 string 类型按 JSON 解析后提交结构化对象（后端按类型校验结构；上面已保证可解析）
  let value: unknown = editText.value
  if (d.type !== 'string') value = JSON.parse(editText.value)
  saving.value = true
  try {
    await operate(siteStore.currentSiteId, instanceId.value, {
      op: 'set', db: db.value, key: d.key, type: d.type, value,
    })
    message.success(t('redis.saved'))
    confirmShow.value = false
    await selectKey({ key: d.key, type: d.type })
    loadInfo()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function deleteKey() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  await operate(siteStore.currentSiteId, instanceId.value, {
    op: 'delete', db: db.value, key: d.key,
  })
  message.success(t('redis.deleted', { key: d.key }))
  clearDetail()
  search(true)
  loadInfo()
}

async function applyTtl() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  await operate(siteStore.currentSiteId, instanceId.value, {
    op: 'expire', db: db.value, key: d.key, ttl: editTtl.value ?? -1,
  })
  message.success(editTtl.value ? t('redis.ttlSet', { n: editTtl.value }) : t('redis.ttlCleared'))
  detail.value = { ...d, ttl: editTtl.value ?? -1 }
  editTtlLoaded.value = editTtl.value
}

// ---------- 新增 Key（左树卡片头入口；set 建 key + 可选 expire 设 TTL） ----------
const addShow = ref(false)
const addKeyName = ref('')
/** 数据类型：非 string 时 value 为纯文本，由后端按类型解析（service._parse_struct_text） */
const addStruct = ref<'string' | 'list' | 'set' | 'hash' | 'zset'>('string')
const addFormat = ref<'text' | 'json'>('text')
const addValue = ref('')
const addTtl = ref<number | null>(null)
const creating = ref(false)

const STRUCT_OPTIONS = ['string', 'list', 'set', 'hash', 'zset'].map((v) => ({ label: v, value: v }))
const addPlaceholder = computed(() => t(`redis.structPh.${addStruct.value}`))

const addJsonInvalid = computed(() => {
  if (addStruct.value !== 'string' || addFormat.value !== 'json') return null
  try {
    JSON.parse(addValue.value)
    return null
  } catch {
    return locateJsonError(addValue.value)
  }
})

function openAdd() {
  addKeyName.value = ''
  addStruct.value = 'string'
  addFormat.value = 'text'
  addValue.value = ''
  addTtl.value = null
  addShow.value = true
}

async function createKey() {
  if (!siteStore.currentSiteId || !instanceId.value) return
  const key = addKeyName.value.trim()
  if (!key) {
    message.error(t('redis.keyRequired'))
    return
  }
  if (addJsonInvalid.value) {
    message.error(t('redis.jsonInvalidSave', { reason: addJsonInvalid.value }))
    return
  }
  creating.value = true
  try {
    // struct 告知后端 value 文本的目标结构（string=list/set/hash/zset 时按行解析）
    await operate(siteStore.currentSiteId, instanceId.value, {
      op: 'set', db: db.value, key, struct: addStruct.value, value: addValue.value,
    })
    if (addTtl.value != null && addTtl.value > 0) {
      await operate(siteStore.currentSiteId, instanceId.value, {
        op: 'expire', db: db.value, key, ttl: addTtl.value,
      })
    }
    message.success(t('redis.created', { key }))
    addShow.value = false
    await search(true)
    loadInfo()
    selectKey({ key, type: addStruct.value })
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    creating.value = false
  }
}

// ---------- 自动刷新 + TTL 活性（5s 轮询列表/info，量随已加载数有界；选中 key 只同步只读 TTL，不打断编辑） ----------
let pollTimer: number | undefined
let tickTimer: number | undefined
const nowSec = ref(Math.floor(Date.now() / 1000))
/** detail.ttl 的取值时刻（秒）：本地每秒倒计时 = ttl - (now - 快照时刻)，避免每秒打后端 */
const ttlAt = ref(0)
watch(detail, () => { ttlAt.value = nowSec.value })

const currentTtl = computed(() => {
  const d = detail.value
  if (!d || d.ttl <= 0) return d?.ttl ?? -1
  return Math.max(0, d.ttl - (nowSec.value - ttlAt.value))
})

/** 用户是否动过编辑区（值或 TTL 输入）：轮询只在"未编辑"时回显后端侧变化 */
function userEditing(): boolean {
  return editText.value !== originalText.value || editTtl.value !== editTtlLoaded.value
}

async function autoRefresh() {
  if (document.hidden || !siteStore.currentSiteId || !instanceId.value) return
  // 单页拉满当前已加载数量：刷新不收缩"加载更多"的列表（树按 key 重建，展开态保留）
  await search(true, true, Math.max(100, keys.value.length))
  loadInfo()
  const sel = selected.value
  if (!sel || userEditing()) return
  try {
    const d = await getKey(siteStore.currentSiteId, instanceId.value, db.value, sel.key)
    if (d.type === 'none') {
      // 后端确认 key 已不存在（删除/过期）才清理——SCAN 分页列表不能当存在性依据
      // （选中 key 在刷新后的首页之外时曾因此误报"已不存在"并清空详情）
      message.info(t('redis.keyGone', { key: sel.key }))
      clearDetail()
      return
    }
    // key 还在（可能只是不在当前列表页）：保留详情并同步 TTL/内存徽章
    detail.value = d
  } catch {
    // 网络/超时等瞬断：不动详情，下一轮再查
  }
}

function startTimers() {
  stopTimers()
  pollTimer = window.setInterval(autoRefresh, 5_000)
  tickTimer = window.setInterval(() => (nowSec.value = Math.floor(Date.now() / 1000)), 1_000)
}
function stopTimers() {
  window.clearInterval(pollTimer)
  window.clearInterval(tickTimer)
}
function onVisibility() {
  if (document.hidden) stopTimers()
  else {
    startTimers()
    autoRefresh()
  }
}

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)}${units[i]}`
}

function fmtTtl(ttl: number): string {
  if (ttl === -1) return t('redis.forever')
  if (ttl === -2) return '-'
  if (ttl <= 0) return t('redis.expiredLabel')
  return `${ttl}s`
}

// ---------- info 指标（带解释 tooltip，文案随语言切换） ----------
const INFO_METRICS = computed(() => {
  const i = info.value
  if (!i) return []
  const infoT = (k: string) => t(`redis.info.${k}.label`)
  const infoTip = (k: string) => t(`redis.info.${k}.tip`)
  return [
    { label: infoT('version'), value: i.version ?? '?', tip: infoTip('version') },
    { label: infoT('memory'), value: fmtBytes(i.memory_used), tip: infoTip('memory') },
    { label: infoT('memoryPeak'), value: fmtBytes(i.memory_peak), tip: infoTip('memoryPeak') },
    { label: infoT('frag'), value: String(i.memory_fragmentation ?? '?'), tip: infoTip('frag') },
    { label: infoT('clients'), value: String(i.connected_clients), tip: infoTip('clients') },
    { label: infoT('hitRate'), value: i.hit_rate != null ? `${i.hit_rate}%` : '?', tip: infoTip('hitRate') },
    { label: t('redis.info.keys.label', { db: db.value }), value: String(i.db_size), tip: infoTip('keys') },
    { label: infoT('expired'), value: String(i.expired_keys), tip: infoTip('expired') },
    { label: infoT('evicted'), value: String(i.evicted_keys), tip: infoTip('evicted') },
    { label: infoT('commands'), value: String(i.total_commands_processed), tip: infoTip('commands') },
  ]
})
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>{{ $t('redis.instance') }}</span>
        <n-select v-model:value="instanceId" size="small" style="width: 200px"
          :placeholder="$t('redis.selectRedis')" :options="instances" />
        <span>{{ $t('redis.db') }}</span>
        <n-select v-model:value="db" size="small" style="width: 160px" :options="DB_OPTIONS"
          :render-label="renderDbLabel" @update:value="refreshDb" />
        <n-input v-model:value="pattern" size="small" style="width: 240px"
          :placeholder="$t('redis.search')" @keyup.enter="refreshDb" />
        <n-button size="small" :loading="loading" :title="$t('redis.manualRefreshTip')" @click="refreshDb">{{ $t('common.refresh') }}</n-button>
        <tab-help topic="redis" />
        <span class="poll-note">{{ $t('redis.autoRefresh') }}</span>
      </n-space>
    </n-card>

    <n-card v-if="info" size="small">
      <n-space :size="20">
        <n-tooltip v-for="m in INFO_METRICS" :key="m.label" trigger="hover" :style="{ maxWidth: '320px' }">
          <template #trigger>
            <span class="metric">
              <span class="metric-label">{{ m.label }}</span>
              <b class="mono">{{ m.value }}</b>
            </span>
          </template>
          {{ m.tip }}
        </n-tooltip>
      </n-space>
    </n-card>

    <!-- 左树右值（RedisDesktop 格局） -->
    <div class="split">
      <n-card size="small" class="left-pane" :title="$t('redis.keys')">
        <template #header-extra>
          <!-- 头部动作条统一 tiny 文本按钮：新增是唯一真实动作（主色 ghost 弱化为轻量入口），
               展开/合并为 quaternary 轻按钮，计数弱化放末尾；窄面板下中英文均单行放下 -->
          <n-space align="center" :size="6" :wrap="false">
            <n-button size="tiny" type="primary" ghost @click="openAdd">{{ $t('redis.add') }}</n-button>
            <n-button size="tiny" quaternary @click="expandAll">{{ $t('redis.expandAll') }}</n-button>
            <n-button size="tiny" quaternary @click="collapseAll">{{ $t('redis.collapseAll') }}</n-button>
            <span class="keys-count">{{ $t('redis.keysCount', { n: keys.length }) }}</span>
          </n-space>
        </template>
        <n-spin :show="loading && !!treeData.length">
          <div class="tree-scroll">
            <n-tree
              v-if="treeData.length"
              v-model:expanded-keys="expandedKeys"
              :data="treeData"
              key-field="key"
              label-field="label"
              children-field="children"
              block-line
              selectable
              :render-label="renderLabel"
              @update:selected-keys="onTreeSelect"
            />
            <!-- 首次加载骨架（替换白屏/转圈，ui-upgrade-design.md §6.2） -->
            <n-skeleton v-else-if="loading" :repeat="5" text class="tree-skel" />
            <div v-else style="text-align: center; color: var(--ops-text-3); padding: 24px 0">{{ $t('redis.noMatch') }}</div>
          </div>
        </n-spin>
        <div v-if="cursor !== 0" style="text-align: center; margin-top: 8px">
          <n-button size="small" :loading="loading" @click="search(false)">{{ $t('redis.loadMore') }}</n-button>
        </div>
      </n-card>

      <n-card size="small" class="right-pane" :title="$t('redis.value')">
        <n-spin :show="detailLoading">
          <template v-if="detail">
            <!-- 头部：彩色类型徽标 + key + TTL/内存徽章 + 刷新 -->
            <div class="detail-head">
              <n-tag size="small" :class="`type-${detail.type}`" :bordered="false">
                {{ detail.type.toUpperCase() }}
              </n-tag>
              <span class="detail-key mono">{{ detail.key }}</span>
              <n-tag size="small" :bordered="false" round>TTL {{ fmtTtl(currentTtl) }}</n-tag>
              <n-tag size="small" :bordered="false" round>
                {{ $t('redis.mem') }} {{ detail.memory_usage != null ? fmtBytes(detail.memory_usage) : '?' }}
              </n-tag>
              <div style="flex: 1" />
              <n-button size="small" @click="refreshValue">{{ $t('common.refresh') }}</n-button>
            </div>

            <!-- Text / Json：CodeMirror 高亮 + 实时校验，两种视图都可直接编辑 -->
            <div class="value-toolbar">
              <n-radio-group :value="format" size="small" @update:value="switchFormat">
                <n-radio-button value="text">Text</n-radio-button>
                <n-radio-button value="json">Json</n-radio-button>
              </n-radio-group>
              <div style="flex: 1" />
            </div>

            <diff-json-editor v-if="format === 'json'" :original="originalText" v-model="editText" height="420px" />
            <n-input v-else v-model:value="editText" type="textarea"
              :rows="16" :input-props="{ spellcheck: false }" class="mono" />

            <!-- JSON 语法错误横幅（编辑器与操作行之间，紧凑样式）：编辑器内有红波浪线
                 +浅红底色，这里给出行/列定位（Json 视图，或 JSON 值的 key 在 Text 视图被改坏） -->
            <n-alert v-if="jsonInvalid" type="error" :show-icon="false" :class="{ shake: bannerShake }"
              style="margin-top: 6px" :theme-overrides="{ padding: '4px 12px', fontSize: '12px' }">
              {{ $t('redis.jsonInvalidTitle') }} — {{ jsonInvalid }}
            </n-alert>

            <!-- TTL / 删除 / 保存（按钮规格统一：small 实心） -->
            <div class="detail-actions">
              <span>{{ $t('redis.ttlSec') }}</span>
              <n-input-number v-model:value="editTtl" size="small" :min="1" style="width: 130px"
                :placeholder="$t('redis.ttlPh')" />
              <n-button size="small" @click="applyTtl">{{ $t('redis.applyTtl') }}</n-button>
              <div style="flex: 1" />
              <countdown-confirm :label="$t('common.delete')" :target="detail.key" :seconds="3" @confirm="deleteKey" />
              <!-- 不禁用按钮：点击时校验并弹明确错误（禁用会让用户不知道为何点不了）；
                   校验必须在开弹窗前做：弹窗内 toast 会被遮罩盖住（见 openSaveConfirm 注释） -->
              <n-button size="small" type="primary" :loading="saving"
                @click="openSaveConfirm">{{ $t('common.save') }}</n-button>
            </div>
          </template>
          <div v-else style="text-align: center; color: #999; padding: 60px 0">
            {{ $t('redis.clickHint') }}
          </div>
        </n-spin>
      </n-card>
    </div>

    <!-- 保存确认对话框（PRD §11.4） -->
    <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="confirmShow" preset="card" :title="$t('redis.confirmSave')" style="width: 520px">
      <p>{{ $t('redis.writeKey') }} <b class="mono">{{ detail?.key }}</b></p>
      <template #footer>
        <div style="display: flex; justify-content: end; gap: 8px">
          <n-button size="small" @click="confirmShow = false">{{ $t('common.cancel') }}</n-button>
          <n-button size="small" type="primary" :loading="saving"
            @click="saveValue">{{ $t('redis.confirmWrite') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 新增 Key：按数据类型 set 建 key（非 string 由后端按行解析文本）+ 可选 expire 设 TTL -->
    <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="addShow" preset="card" :title="$t('redis.addKey')" style="width: 520px">
      <div class="add-field">
        <span>{{ $t('redis.keyName') }}</span>
        <n-input v-model:value="addKeyName" class="mono" :placeholder="$t('redis.keyNamePh')"
          :input-props="{ spellcheck: false }" />
      </div>
      <div class="add-field">
        <span>{{ $t('redis.keyStruct') }}</span>
        <n-select v-model:value="addStruct" size="small" :options="STRUCT_OPTIONS" />
      </div>
      <!-- Text/Json 只是 string 类型的值格式提示；list/set/hash/zset 均为按行文本 -->
      <div v-if="addStruct === 'string'" class="add-field">
        <span>{{ $t('redis.keyType') }}</span>
        <n-radio-group v-model:value="addFormat" size="small">
          <n-radio-button value="text">Text</n-radio-button>
          <n-radio-button value="json">Json</n-radio-button>
        </n-radio-group>
      </div>
      <div class="add-field">
        <span>{{ $t('redis.initialValue') }}</span>
        <n-input v-model:value="addValue" type="textarea" :rows="6" class="mono"
          :placeholder="addPlaceholder" :input-props="{ spellcheck: false }" />
        <n-alert v-if="addJsonInvalid" type="error" :show-icon="false" style="margin-top: 6px">
          {{ $t('redis.jsonInvalidTitle') }} — {{ addJsonInvalid }}
        </n-alert>
      </div>
      <div class="add-field">
        <span>{{ $t('redis.ttlOptional') }}</span>
        <n-input-number v-model:value="addTtl" size="small" :min="1" style="width: 100%" />
      </div>
      <template #footer>
        <div style="display: flex; justify-content: end; gap: 8px">
          <n-button size="small" @click="addShow = false">{{ $t('common.cancel') }}</n-button>
          <n-button size="small" type="primary" :loading="creating"
            @click="createKey">{{ $t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>
  </n-space>
</template>

<style scoped>
.split {
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.left-pane {
  width: 360px;
  flex: none;
}
.right-pane {
  flex: 1;
  min-width: 0;
}
.tree-scroll {
  max-height: calc(100vh - 320px);
  overflow: auto;
}
/* 顶栏自动刷新频率注记（对齐 Server 页 poll-note） */
.poll-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
/* Keys 头部计数（与按钮同高垂直居中，弱化灰） */
.keys-count {
  color: #999;
  font-size: 12px;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.detail-key {
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}
/* 类型徽标着色（对齐 RedisDesktop 的类型辨识度） */
.type-string { background: #18a058; color: #fff; }
.type-hash { background: #0b63ce; color: #fff; }
.type-list { background: #f0a020; color: #fff; }
.type-set { background: #722ed1; color: #fff; }
.type-zset { background: #d03050; color: #fff; }
.value-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.detail-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.add-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.add-field > span {
  font-size: 13px;
  color: var(--ops-text-2);
}
.metric {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  font-size: 13px;
  color: var(--ops-text-2);
  cursor: help;
  border-bottom: 1px dashed var(--ops-border);
  padding-bottom: 1px;
}
.metric b {
  color: var(--ops-text-1);
}
.metric .mono {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
</style>

<style>
/* 树节点：文件夹与叶子样式统一；目录行 label 铺满整行接管点击 */
.tree-label {
  font-size: 13px;
}
.tree-dir-row {
  display: block;
  cursor: pointer;
}
.tree-count {
  color: #999;
  font-size: 12px;
  margin-left: 6px;
}
/* DB 下拉选项：DB5 [102]，数字灰色弱化（dropdown 挂 body，样式需全局） */
.db-option .db-count {
  color: #b0b3b8;
  font-size: 12px;
  margin-left: 8px;
}
/* JSON 错误横幅抖动（保存被拦截时的就地反馈；keyframes 放全局避免 scoped 改名） */
.shake {
  animation: ops-shake 0.3s ease-in-out 1;
}
@keyframes ops-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
</style>
