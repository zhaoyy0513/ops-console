<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertCircle, ChevronDown, ChevronRight, Database, LoaderCircle, Search, Server, WandSparkles } from 'lucide-vue-next'
import { parser as jsonParser } from '@lezer/json'
import { message } from '@/lib/message'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import TooltipContent from '@/components/ui/tooltip/TooltipContent.vue'
import { Textarea } from '@/components/ui/textarea'
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

/** DB 下拉：label 'DB5'，行内数字后跟灰色 [key 数] */
const DB_OPTIONS = computed(() =>
  Array.from({ length: 16 }, (_, i) => ({
    label: `DB${i}`,
    value: i,
  })),
)

function dbCount(v: number): number | null {
  const n = info.value?.db_sizes?.[v]
  return n != null ? n : null
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
async function search(reset = true, silent = false, count = 500) {
  // 首屏 500：SCAN 单批 100 时同一前缀的分组会分批到达，树按已加载 key 分组
  // 导致分组计数偏小（如 ALERT_CONFIG 只显示 1 个），点"加载更多"才补全。
  // 内网库规模小，500 基本一次拉全；大库仍走分页。
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

// ---------- 树（':' 分层折叠 + 自然排序；点击整行展开/折叠） ----------

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

const treeData = computed(() => buildTree(keys.value))

/** 深度展开的渲染序：目录在其展开时才进列表（自绘树替代 NTree，任意深度可用） */
const flatTree = computed(() => {
  const out: Array<{ node: TreeNode; depth: number }> = []
  const walk = (nodes: TreeNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ node: n, depth })
      if (n.dir && expandedKeys.value.includes(n.key)) walk(n.children, depth + 1)
    }
  }
  walk(treeData.value, 0)
  return out
})

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
  walk(treeData.value)
  expandedKeys.value = out
}
function collapseAll() {
  expandedKeys.value = []
}

/** 弹窗不响应 Esc / 点遮罩关闭（对齐原 mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
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

/** 格式化当前 Json 编辑内容（不改变 diff 基线，仅重排缩进；仅 Json 视图可用） */
function formatJson() {
  if (format.value !== 'json') return
  try {
    editText.value = JSON.stringify(JSON.parse(editText.value), null, 2)
  } catch {
    message.warning(t('redis.jsonInvalidTitle'))
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
 *  toast 挂 body 顶层，但确认弹窗遮罩之上仍可能盖住，统一在弹窗外报错 */
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
  await search(true, true, Math.max(500, keys.value.length))
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
/** 不可用字段显示 '-'（缺失 ≠ 0）；tone 决定标黄/标红 */
function fmtNum(n: number | null | undefined): string {
  return n == null ? '-' : String(n)
}

const INFO_METRICS = computed(() => {
  const i = info.value
  if (!i) return []
  const infoT = (k: string) => t(`redis.info.${k}.label`)
  const infoTip = (k: string) => t(`redis.info.${k}.tip`)
  // maxmemory=0 表示未设上限；缺失显示 '-'
  const memMax = i.memory_max == null
    ? '-'
    : i.memory_max === 0
      ? t('redis.info.unlimited')
      : fmtBytes(i.memory_max)
  const persist = [i.rdb_last_bgsave_status, i.aof_last_bgrewrite_status]
    .map((s) => s ?? '-')
    .join(' / ')
  const persistBad = [i.rdb_last_bgsave_status, i.aof_last_bgrewrite_status]
    .some((s) => s != null && s !== 'ok')
  return [
    {
      label: infoT('hitRate'),
      value: i.hit_rate != null ? `${i.hit_rate}%` : '-',
      tip: infoTip('hitRate'),
      tone: i.hit_rate != null && i.hit_rate < 80 ? 'warn' : '',
    },
    { label: infoT('memory'), value: `${fmtBytes(i.memory_used)} / ${memMax}`, tip: infoTip('memory'), tone: '' },
    {
      label: infoT('frag'),
      value: i.memory_fragmentation != null ? String(i.memory_fragmentation) : '-',
      tip: infoTip('frag'),
      tone: i.memory_fragmentation != null && i.memory_fragmentation > 1.5 ? 'warn' : '',
    },
    { label: infoT('clients'), value: fmtNum(i.connected_clients), tip: infoTip('clients'), tone: '' },
    {
      label: infoT('blocked'),
      value: fmtNum(i.blocked_clients),
      tip: infoTip('blocked'),
      tone: i.blocked_clients ? 'warn' : '',
    },
    {
      label: infoT('rejected'),
      value: fmtNum(i.rejected_connections),
      tip: infoTip('rejected'),
      tone: i.rejected_connections ? 'crit' : '',
    },
    {
      label: infoT('evicted'),
      value: fmtNum(i.evicted_keys),
      tip: infoTip('evicted'),
      tone: i.evicted_keys ? 'crit' : '',
    },
    { label: infoT('ops'), value: fmtNum(i.ops_per_sec), tip: infoTip('ops'), tone: '' },
    { label: infoT('persistence'), value: persist, tip: infoTip('persistence'), tone: persistBad ? 'crit' : '' },
    { label: t('redis.info.keys.label', { db: db.value }), value: fmtNum(i.db_size), tip: infoTip('keys'), tone: '' },
    { label: infoT('expired'), value: fmtNum(i.expired_keys), tip: infoTip('expired'), tone: '' },
    { label: infoT('commands'), value: fmtNum(i.total_commands_processed), tip: infoTip('commands'), tone: '' },
    { label: infoT('memoryPeak'), value: fmtBytes(i.memory_peak), tip: infoTip('memoryPeak'), tone: '' },
    { label: infoT('version'), value: i.version ?? '-', tip: infoTip('version'), tone: '' },
  ]
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card class="p-3">
      <!-- 工具栏：实例 / DB / 搜索 / 刷新 收进一条紧凑控制条。
           分组用分隔线而不是裸标签，窄屏才折行（标签 inline 在同一行内，不单独占位） -->
      <div class="flex flex-wrap items-center gap-2">
        <div class="tool-group">
          <Server class="tool-icon" />
          <Select
            class="w-[190px] max-w-full"
            :model-value="instanceId ?? ''"
            @update:model-value="(v: unknown) => (instanceId = (v as string) || null)"
          >
            <SelectTrigger :placeholder="$t('redis.selectRedis')" />
            <SelectContent>
              <SelectItem v-for="o in instances" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <span class="tool-sep" />
        <div class="tool-group">
          <Database class="tool-icon" />
          <Select
            class="w-[150px] max-w-full"
            :model-value="String(db)"
            @update:model-value="(v: unknown) => { db = Number(v); refreshDb() }"
          >
            <SelectTrigger :placeholder="`DB${db}`" />
            <SelectContent>
              <SelectItem v-for="o in DB_OPTIONS" :key="o.value" :value="String(o.value)">
                DB{{ o.value }}<span v-if="dbCount(o.value) !== null" class="db-count">  [{{ dbCount(o.value) }}]</span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <span class="tool-sep" />
        <!-- 搜索：图标 + 输入框 + 回车即查 -->
        <div class="tool-group search-group">
          <Search class="tool-icon" />
          <Input
            v-model="pattern"
            class="w-[230px] max-w-full"
            :placeholder="$t('redis.search')"
            @keyup.enter="refreshDb"
          />
        </div>
        <Button variant="outline" size="sm" :disabled="loading" :title="$t('redis.manualRefreshTip')" @click="refreshDb">
          <LoaderCircle v-if="loading" class="animate-spin" />
          {{ $t('common.refresh') }}
        </Button>
        <tab-help topic="redis" />
        <span class="poll-note">{{ $t('redis.autoRefresh') }}</span>
      </div>
    </Card>

    <Card v-if="info" class="p-3">
      <div class="flex flex-wrap items-center gap-5">
        <!-- 从节点徽标：slave 才显示（主从只读副本，写入会失败） -->
        <Badge v-if="info.role === 'slave'" variant="warning" size="sm">{{ $t('redis.info.roleSlave') }}</Badge>
        <TooltipProvider>
          <TooltipRoot v-for="m in INFO_METRICS" :key="m.label" :delay-duration="100">
          <TooltipTrigger as-child>
            <span class="metric">
              <span class="metric-label">{{ m.label }}</span>
              <b class="metric-value font-mono" :class="m.tone ? `tone-${m.tone}` : ''">{{ m.value }}</b>
            </span>
          </TooltipTrigger>
          <TooltipContent class="max-w-80 whitespace-pre-line">
            <span class="text-xs">{{ m.tip }}</span>
          </TooltipContent>
          </TooltipRoot>
        </TooltipProvider>
      </div>
    </Card>

    <!-- 左树右值（RedisDesktop 格局） -->
    <div class="split">
      <Card class="left-pane">
        <CardHeader class="pb-1">
          <!-- CardTitle 默认插槽 / 按钮组走 action 插槽：CardHeader justify-between 把按钮推到行最右 -->
          <CardTitle>{{ $t('redis.keys') }}</CardTitle>
          <template #action>
            <!-- 头部动作条：新增是唯一真实动作（主色），展开/收起轻量 outline；计数弱化放末尾 -->
            <div class="flex flex-wrap items-center justify-end gap-1.5">
              <Button variant="outline" size="sm" class="text-primary" @click="openAdd">{{ $t('redis.add') }}</Button>
              <Button variant="ghost" size="sm" @click="expandAll">{{ $t('redis.expandAll') }}</Button>
              <Button variant="ghost" size="sm" @click="collapseAll">{{ $t('redis.collapseAll') }}</Button>
              <span class="keys-count">{{ $t('redis.keysCount', { n: keys.length }) }}</span>
            </div>
          </template>
        </CardHeader>
        <CardContent>
          <div class="tree-scroll" style="position: relative">
            <!-- 自绘折叠树（替代 NTree）：目录行整行点击展开/折叠，叶子行点击开详情；
                 v-for 的 key 用 key 名（D: 前缀目录 / L: 前缀叶子），深浅展开态由 flatTree 决定 -->
            <template v-if="treeData.length">
              <template v-for="{ node, depth } in flatTree" :key="node.key">
                <div
                  v-if="node.dir"
                  class="tree-row tree-dir"
                  :style="{ paddingLeft: `${6 + depth * 16}px` }"
                  @click="toggleDir(node)"
                >
                  <ChevronDown v-if="expandedKeys.includes(node.key)" class="tree-arrow flex-none" />
                  <ChevronRight v-else class="tree-arrow flex-none" />
                  <span class="truncate">{{ node.label }}</span>
                  <span class="tree-count">({{ node.count }})</span>
                </div>
                <div
                  v-else
                  class="tree-row tree-leaf font-mono"
                  :style="{ paddingLeft: `${6 + depth * 16}px` }"
                  :class="{ active: selected?.key === node.item.key }"
                  :title="node.item.key"
                  @click="selectKey(node.item)"
                >
                  <!-- 与箭头等宽的透明占位，保证叶子文本与目录文本左缘对齐 -->
                  <span class="size-4 flex-none" />
                  <span class="truncate">{{ node.item.key }}</span>
                </div>
              </template>
            </template>
            <!-- 首次加载骨架 -->
            <div v-else-if="loading" class="flex flex-col gap-2 p-1">
              <Skeleton v-for="i in 5" :key="i" class="h-4 w-full" />
            </div>
            <div v-else class="py-6 text-center text-sm text-muted-foreground">{{ $t('redis.noMatch') }}</div>
          </div>
          <div v-if="cursor !== 0" class="mt-2 text-center">
            <Button variant="outline" size="sm" :disabled="loading" @click="search(false)">
              <LoaderCircle v-if="loading" class="animate-spin" />
              {{ $t('redis.loadMore') }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card class="right-pane">
        <CardHeader class="pb-1"><CardTitle>{{ $t('redis.value') }}</CardTitle></CardHeader>
        <CardContent style="position: relative">
          <div v-if="detailLoading" class="absolute inset-0 z-10 flex items-center justify-center bg-card/70">
            <LoaderCircle class="size-6 animate-spin text-muted-foreground" />
          </div>
          <template v-if="detail">
            <!-- 头部：彩色类型徽标 + key + TTL/内存徽章 + 刷新 -->
            <div class="detail-head">
              <Badge size="sm" :class="`type-${detail.type}`">{{ detail.type.toUpperCase() }}</Badge>
              <span class="detail-key font-mono">{{ detail.key }}</span>
              <Badge variant="secondary" size="sm" class="rounded-full">TTL {{ fmtTtl(currentTtl) }}</Badge>
              <Badge variant="secondary" size="sm" class="rounded-full">
                {{ $t('redis.mem') }} {{ detail.memory_usage != null ? fmtBytes(detail.memory_usage) : '?' }}
              </Badge>
              <div class="flex-1" />
              <Button variant="outline" size="sm" @click="refreshValue">{{ $t('common.refresh') }}</Button>
            </div>

            <!-- Text / Json 切换 + CodeMirror（两种视图都可直接编辑） -->
            <div class="value-toolbar">
              <div class="fmt-toggle">
                <button type="button" class="fmt-btn" :class="{ on: format === 'text' }" @click="switchFormat('text')">Text</button>
                <button type="button" class="fmt-btn" :class="{ on: format === 'json' }" @click="switchFormat('json')">Json</button>
              </div>
              <div class="flex-1" />
              <Button variant="outline" size="sm" :disabled="format !== 'json'" :title="$t('redis.formatJson')" @click="formatJson">
                <WandSparkles />
                {{ $t('redis.formatJson') }}
              </Button>
            </div>

            <!-- JSON 语法错误横幅（编辑器上方，与编辑动线零距离）：编辑器内有红波浪线
                 +浅红底色，这里给出行/列定位（Json 视图，或 JSON 值的 key 在 Text 视图被改坏）。
                 放在编辑器之上是因为错误提示必须紧跟用户视线焦点，放下面会被操作栏挤到视野外 -->
            <div v-if="jsonInvalid" :class="['json-banner', { shake: bannerShake }]">
              <AlertCircle class="json-banner-icon" />
              {{ $t('redis.jsonInvalidTitle') }} — {{ jsonInvalid }}
            </div>

            <diff-json-editor v-if="format === 'json'" :original="originalText" v-model="editText" height="420px" />
            <Textarea v-else v-model="editText" :rows="16" :spellcheck="false" class="font-mono" />

            <!-- TTL / 删除 / 保存（small 实心） -->
            <div class="detail-actions">
              <span>{{ $t('redis.ttlSec') }}</span>
              <Input
                :model-value="editTtl ?? ''"
                type="number"
                :min="1"
                class="w-[130px]"
                :placeholder="$t('redis.ttlPh')"
                @update:model-value="(v: unknown) => (editTtl = v === '' ? null : Number(v))"
                @keydown.enter="applyTtl"
              />
              <Button variant="outline" size="sm" @click="applyTtl">{{ $t('redis.applyTtl') }}</Button>
              <div class="flex-1" />
              <countdown-confirm :label="$t('common.delete')" :target="detail.key" :seconds="3" :on-confirm="deleteKey" />
              <!-- 不禁用按钮：点击时校验并弹明确错误（禁用会让用户不知道为何点不了）；
                   校验必须在开弹窗前做（见 openSaveConfirm 注释） -->
              <Button size="sm" :disabled="saving" @click="openSaveConfirm">
                <LoaderCircle v-if="saving" class="animate-spin" />
                {{ $t('common.save') }}
              </Button>
            </div>
          </template>
          <div v-else class="py-15 text-center text-sm text-muted-foreground">
            {{ $t('redis.clickHint') }}
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 保存确认对话框（PRD §11.4） -->
    <Dialog :open="confirmShow" @update:open="(v: boolean) => (confirmShow = v)">
      <DialogContent class="w-[520px] max-w-[94vw]" @escape-key-down="blockDismiss" @interact-outside="blockDismiss">
        <DialogHeader>
          <DialogTitle>{{ $t('redis.confirmSave') }}</DialogTitle>
        </DialogHeader>
        <p class="text-sm">{{ $t('redis.writeKey') }} <b class="font-mono">{{ detail?.key }}</b></p>
        <div class="flex justify-end gap-2">
          <Button variant="outline" size="sm" @click="confirmShow = false">{{ $t('common.cancel') }}</Button>
          <Button size="sm" :disabled="saving" @click="saveValue">
            <LoaderCircle v-if="saving" class="animate-spin" />
            {{ $t('redis.confirmWrite') }}
          </Button>
        </div>
      </DialogContent>
    </Dialog>

    <!-- 新增 Key：按数据类型 set 建 key（非 string 由后端按行解析文本）+ 可选 expire 设 TTL -->
    <Dialog :open="addShow" @update:open="(v: boolean) => (addShow = v)">
      <DialogContent class="w-[520px] max-w-[94vw]" @escape-key-down="blockDismiss" @interact-outside="blockDismiss">
        <DialogHeader>
          <DialogTitle>{{ $t('redis.addKey') }}</DialogTitle>
        </DialogHeader>
        <div class="add-field">
          <span>{{ $t('redis.keyName') }}</span>
          <Input v-model="addKeyName" class="font-mono" :placeholder="$t('redis.keyNamePh')" :spellcheck="false" />
        </div>
        <div class="add-field">
          <span>{{ $t('redis.keyStruct') }}</span>
          <Select :model-value="addStruct" @update:model-value="(v: unknown) => (addStruct = v as 'string' | 'list' | 'set' | 'hash' | 'zset')">
            <SelectTrigger :placeholder="addStruct" />
            <SelectContent>
              <SelectItem v-for="o in STRUCT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <!-- Text/Json 只是 string 类型的值格式提示；list/set/hash/zset 均为按行文本 -->
        <div v-if="addStruct === 'string'" class="add-field">
          <span>{{ $t('redis.keyType') }}</span>
          <div class="fmt-toggle">
            <button type="button" class="fmt-btn" :class="{ on: addFormat === 'text' }" @click="addFormat = 'text'">Text</button>
            <button type="button" class="fmt-btn" :class="{ on: addFormat === 'json' }" @click="addFormat = 'json'">Json</button>
          </div>
        </div>
        <div class="add-field">
          <span>{{ $t('redis.initialValue') }}</span>
          <div v-if="addJsonInvalid" :class="['json-banner', 'add-json-banner']">
            <AlertCircle class="json-banner-icon" />
            {{ $t('redis.jsonInvalidTitle') }} — {{ addJsonInvalid }}
          </div>
          <Textarea v-model="addValue" :rows="6" class="font-mono" :placeholder="addPlaceholder" :spellcheck="false" />
        </div>
        <div class="add-field">
          <span>{{ $t('redis.ttlOptional') }}</span>
          <Input
            :model-value="addTtl ?? ''"
            type="number"
            :min="1"
            class="w-full"
            placeholder="TTL"
            @update:model-value="(v: unknown) => (addTtl = v === '' ? null : Number(v))"
          />
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="outline" size="sm" @click="addShow = false">{{ $t('common.cancel') }}</Button>
          <Button size="sm" :disabled="creating" @click="createKey">
            <LoaderCircle v-if="creating" class="animate-spin" />
            {{ $t('common.save') }}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.split {
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-width: 0;
}
.left-pane {
  width: 360px;
  flex: none;
  max-width: 100%;
}
.right-pane {
  flex: 1;
  min-width: 0;
}
.tree-scroll {
  max-height: calc(100vh - 100px);
  overflow: auto;
}
/* 窄屏竖向堆叠：树面板占满宽度并限高，保证值面板可见（不出现页面级横向滚动条） */
@media (max-width: 960px) {
  .split {
    flex-direction: column;
  }
  .left-pane {
    width: auto;
  }
  .tree-scroll {
    max-height: 40vh;
  }
}
.tool-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
}
.tool-icon {
  width: 14px;
  height: 14px;
  flex: none;
  color: var(--ops-text-3);
}
.tool-sep {
  width: 1px;
  height: 18px;
  flex: none;
  background: var(--ops-border);
  margin: 0 2px;
}
.search-group :deep(input) {
  padding-left: 8px;
}
.poll-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
.keys-count {
  color: var(--ops-text-3);
  font-size: 12px;
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
  transition: background 120ms;
}
.tree-row:hover {
  background: var(--ops-surface-2);
}
.tree-row.active {
  background: color-mix(in srgb, var(--primary) 12%, transparent);
}
.tree-arrow {
  width: 1rem;
  height: 1rem;
  color: var(--ops-text-3);
}
.tree-dir:hover .tree-arrow {
  color: var(--ops-text-1);
}
.tree-leaf {
  color: var(--ops-text-2);
}
.tree-count {
  color: var(--ops-text-3);
  font-size: 12px;
  margin-left: 4px;
  flex: none;
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
/* Text/Json 切换（自绘分段按钮，替代 NRadioGroup） */
.fmt-toggle {
  display: inline-flex;
  border: 1px solid var(--ops-border);
  border-radius: 6px;
  overflow: hidden;
}
.fmt-btn {
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
  background: transparent;
  color: var(--ops-text-2);
  border: none;
}
.fmt-btn.on {
  background: var(--primary);
  color: var(--primary-foreground);
}
.json-banner {
  /* 位于编辑器上方：下边距与编辑器拉开、上边距贴住工具栏 */
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 4px;
  color: var(--ops-critical);
  background: color-mix(in srgb, var(--ops-critical) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--ops-critical) 30%, transparent);
}
.json-banner-icon {
  width: 14px;
  height: 14px;
  flex: none;
}
.detail-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.add-json-banner {
  margin-top: 6px;
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
.metric-value {
  color: var(--ops-text-1);
  font-variant-numeric: tabular-nums;
}
.metric-value.tone-warn {
  color: var(--ops-warning);
}
.metric-value.tone-crit {
  color: var(--ops-critical);
}
.db-count {
  color: var(--ops-text-3);
  font-size: 12px;
  margin-left: 8px;
}
</style>

<style>
/* JSON 错误横幅抖动（保存被拦截时的就地反馈） */
.shake {
  animation: ops-shake 0.3s ease-in-out 1;
}
@keyframes ops-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
</style>
