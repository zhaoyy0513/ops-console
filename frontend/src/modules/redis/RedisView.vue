<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NModal,
  NRadioGroup,
  NRadioButton,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NTooltip,
  NTree,
  useMessage,
  type TreeOption,
} from 'naive-ui'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import BaseChart from '../../components/BaseChart.vue'
import { getSamples, type SamplePoint } from '../overview/api'
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

// ---------- 实例 / DB / 搜索 ----------
const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const db = ref(0)
const pattern = ref('')
const typeFilter = ref<string | null>(null)
const typeOptions = [
  { label: '全部类型', value: '' },
  { label: 'string', value: 'string' },
  { label: 'hash', value: 'hash' },
  { label: 'list', value: 'list' },
  { label: 'set', value: 'set' },
  { label: 'zset', value: 'zset' },
]

const keys = ref<KeyItem[]>([])
const cursor = ref(0)
const loading = ref(false)
const info = ref<RedisInfo | null>(null)
const memSeries = ref<SamplePoint[]>([])

const DB_OPTIONS = Array.from({ length: 16 }, (_, i) => ({ label: `DB ${i}`, value: i }))

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

async function search(reset = true) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  loading.value = true
  try {
    const page = await listKeys(siteStore.currentSiteId, instanceId.value, {
      db: db.value,
      pattern: pattern.value.trim(),
      cursor: reset ? 0 : cursor.value,
      count: 100,
      type: typeFilter.value || undefined,
    })
    keys.value = reset ? page.keys : [...keys.value, ...page.keys]
    cursor.value = page.cursor
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadInfo() {
  if (!siteStore.currentSiteId || !instanceId.value) return
  try {
    info.value = await getInfo(siteStore.currentSiteId, instanceId.value, db.value)
    // 内存趋势（overview 任务 30s 采样）
    getSamples(`redis:${instanceId.value}`, 'mem')
      .then((s) => (memSeries.value = [...s].reverse()))
      .catch(() => {})
  } catch {
    info.value = null
  }
}

function doSearch() {
  search(true)
  loadInfo()
}

onMounted(loadInstances)
watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  keys.value = []
  info.value = null
  selected.value = null
  loadInstances()
})
watch(instanceId, () => {
  selected.value = null
  search(true)
  loadInfo()
})

// ---------- 树（RedisDesktop 风格：':' 分层折叠 + 计数，节点样式统一） ----------

interface TreeDir { key: string; label: string; dir: true; children: TreeNode[]; count: number }
interface TreeLeaf { key: string; label: string; dir: false; item: KeyItem }
type TreeNode = TreeDir | TreeLeaf

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

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
        // 叶子显示完整 key（与 RedisDesktop 一致）
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

function renderLabel({ option }: { option: TreeOption }) {
  const node = option as unknown as TreeNode
  if (node.dir) {
    return h('span', { class: 'tree-label' }, [
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

// ---------- 详情（左树右值；Text/Json 自动感知） ----------
const selected = ref<KeyItem | null>(null)
const detail = ref<KeyDetail | null>(null)
const detailLoading = ref(false)
const format = ref<'text' | 'json'>('text') // 自动检测默认；json=只读高亮，text=可编辑
const editText = ref('')
const editTtl = ref<number | null>(null)
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

/** 轻量 JSON 语法高亮（key 蓝 / string 绿 / number 红 / bool-null 橙）；过大退化为纯文本 */
function highlightJson(src: string): string {
  if (src.length > 200_000) return src
  const esc = src.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (m) => {
      let cls = 'jnum'
      if (m.startsWith('"')) cls = m.trimEnd().endsWith(':') ? 'jkey' : 'jstr'
      else if (/^(true|false|null)$/.test(m)) cls = 'jbool'
      return `<span class="${cls}">${m}</span>`
    },
  )
}

const parsedJson = computed(() => {
  if (format.value !== 'json' || !isJson(editText.value)) return null
  try {
    return JSON.stringify(JSON.parse(editText.value), null, 2)
  } catch {
    return null
  }
})

/** 详情打开时自动感知：能 parse 成 object/array 的 value 默认 Json 视图 */
async function selectKey(k: KeyItem) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  selected.value = k
  detailLoading.value = true
  try {
    detail.value = await getKey(siteStore.currentSiteId, instanceId.value, db.value, k.key)
    const raw = toEditText(detail.value)
    editText.value = raw
    format.value = isJson(raw) ? 'json' : 'text'
    editTtl.value = detail.value.ttl > 0 ? detail.value.ttl : null
  } catch (e) {
    message.error((e as Error).message)
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

function toEditText(d: KeyDetail): string {
  const v = d.value
  if (d.type === 'string') return String(v ?? '')
  return JSON.stringify(v ?? null, null, 2)
}

function prettyFill() {
  try {
    editText.value = JSON.stringify(JSON.parse(editText.value), null, 2)
  } catch {
    message.error('不是合法 JSON，无法格式化')
  }
}

const changeSummary = computed(() => {
  const d = detail.value
  if (!d) return ''
  const preview = editText.value.length > 160 ? `${editText.value.slice(0, 160)}…` : editText.value
  return `${d.type.toUpperCase()} · ${editText.value.length} chars\n${preview}`
})

async function saveValue() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  // 非 string 类型按 JSON 解析后提交结构化对象（后端按类型校验结构）
  let value: unknown = editText.value
  if (d.type !== 'string') {
    if (!isJson(editText.value)) {
      message.error('JSON 格式错误，请检查后再保存')
      return
    }
    value = JSON.parse(editText.value)
  }
  saving.value = true
  try {
    await operate(siteStore.currentSiteId, instanceId.value, {
      op: 'set', db: db.value, key: d.key, type: d.type, value,
    })
    message.success('已保存')
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
  message.success(`已删除 ${d.key}`)
  selected.value = null
  detail.value = null
  search(true)
  loadInfo()
}

async function applyTtl() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  await operate(siteStore.currentSiteId, instanceId.value, {
    op: 'expire', db: db.value, key: d.key, ttl: editTtl.value ?? -1,
  })
  message.success(editTtl.value ? `TTL 已设为 ${editTtl.value}s` : 'TTL 已清除')
  detail.value = { ...d, ttl: editTtl.value ?? -1 }
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
  if (ttl === -1) return '永久'
  if (ttl === -2) return '-'
  return `${ttl}s`
}

const memTrendOption = computed(() => ({
  grid: { left: 64, right: 16, top: 20, bottom: 26 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: memSeries.value.map((p) => new Date(p.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
  },
  yAxis: { type: 'value', axisLabel: { formatter: (v: number) => `${Math.round(v / 1024 / 1024)}M` } },
  series: [{
    name: '内存',
    type: 'line',
    data: memSeries.value.map((p) => p.v),
    smooth: true,
    showSymbol: false,
    areaStyle: { opacity: 0.15 },
    lineStyle: { color: '#237804' },
    itemStyle: { color: '#237804' },
  }],
}))

// ---------- info 指标（带中文解释） ----------
const INFO_METRICS = computed(() => {
  const i = info.value
  if (!i) return []
  return [
    { label: '版本', value: i.version ?? '?', tip: 'Redis 服务端版本' },
    { label: '内存', value: fmtBytes(i.memory_used), tip: '当前数据占用的内存（含缓冲）' },
    { label: '内存峰值', value: fmtBytes(i.memory_peak), tip: '历史最高内存，用于容量规划参考' },
    { label: '碎片率', value: String(i.memory_fragmentation ?? '?'),
      tip: '物理内存/逻辑内存之比：>1.5 碎片偏高（可考虑重启回收）；<1 表示内存不足已动用 swap，需警惕' },
    { label: '客户端', value: String(i.connected_clients),
      tip: '当前连接数（含本平台）；持续增长可能意味着连接泄漏' },
    { label: '命中率', value: i.hit_rate != null ? `${i.hit_rate}%` : '?',
      tip: '读请求直接命中的比例；长期偏低说明业务查询的 key 大多不存在，或缓存设计/容量有问题' },
    { label: `Keys(DB${db.value})`, value: String(i.db_size), tip: '当前所选 DB 的 key 总数' },
    { label: '过期删除', value: String(i.expired_keys), tip: '启动以来到期自动删除的 key 累计数' },
    { label: '内存淘汰', value: String(i.evicted_keys),
      tip: '内存满后按策略挤出的 key 数；>0 说明曾发生内存不足，被淘汰的 key 丢了' },
    { label: '累计命令', value: String(i.total_commands_processed), tip: '启动以来处理的命令总数' },
  ]
})
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>实例</span>
        <n-select v-model:value="instanceId" size="small" style="width: 200px"
          placeholder="选择 Redis" :options="instances" />
        <n-select v-model:value="db" size="small" style="width: 110px" :options="DB_OPTIONS"
          @update:value="doSearch" />
        <n-input v-model:value="pattern" size="small" style="width: 240px"
          placeholder="模糊搜索，忽略大小写" @keyup.enter="doSearch" />
        <n-select v-model:value="typeFilter" size="small" style="width: 130px"
          :options="typeOptions" @update:value="doSearch" />
        <n-button size="small" :loading="loading" @click="doSearch">搜索</n-button>
      </n-space>
    </n-card>

    <n-card v-if="info" size="small">
      <n-space :size="20">
        <n-tooltip v-for="m in INFO_METRICS" :key="m.label" trigger="hover" :style="{ maxWidth: '320px' }">
          <template #trigger>
            <span class="metric">
              <span class="metric-label">{{ m.label }}</span>
              <b>{{ m.value }}</b>
            </span>
          </template>
          {{ m.tip }}
        </n-tooltip>
      </n-space>
    </n-card>

    <n-card v-if="info && memSeries.length" size="small" title="内存趋势（30s 采样）">
      <base-chart :option="memTrendOption" height="160px" />
    </n-card>

    <!-- 左树右值（RedisDesktop 格局） -->
    <div class="split">
      <n-card size="small" class="left-pane" title="Keys">
        <template #header-extra>
          <span style="color: #999; font-size: 12px">{{ keys.length }} 条</span>
        </template>
        <n-spin :show="loading">
          <div class="tree-scroll">
            <n-tree
              v-if="treeData.length"
              :data="treeData"
              key-field="key"
              label-field="label"
              children-field="children"
              block-line
              selectable
              :render-label="renderLabel"
              @update:selected-keys="onTreeSelect"
            />
            <div v-else style="text-align: center; color: #999; padding: 24px 0">无匹配 Key</div>
          </div>
        </n-spin>
        <div v-if="cursor !== 0" style="text-align: center; margin-top: 8px">
          <n-button size="small" :loading="loading" @click="search(false)">Load More</n-button>
        </div>
      </n-card>

      <n-card size="small" class="right-pane" title="Value">
        <n-spin :show="detailLoading">
          <template v-if="detail">
            <!-- 头部：类型 + key + TTL/内存 -->
            <div class="detail-head">
              <n-tag size="small">{{ detail.type.toUpperCase() }}</n-tag>
              <span class="detail-key mono">{{ detail.key }}</span>
              <span class="detail-meta">TTL <b>{{ fmtTtl(detail.ttl) }}</b></span>
              <span class="detail-meta">
                内存 <b>{{ detail.memory_usage != null ? fmtBytes(detail.memory_usage) : '?' }}</b>
              </span>
            </div>

            <!-- Text / Json 切换（自动感知默认；value 不是 JSON 时 Json 不可选） -->
            <div class="value-toolbar">
              <n-radio-group v-model:value="format" size="small">
                <n-radio-button value="text">Text</n-radio-button>
                <n-radio-button value="json" :disabled="!isJson(editText)">Json</n-radio-button>
              </n-radio-group>
              <span v-if="format === 'json'" class="hint">Json 视图只读，编辑请切到 Text</span>
              <div style="flex: 1" />
              <n-button v-if="format === 'text' && isJson(editText)" size="tiny" @click="prettyFill">格式化</n-button>
            </div>

            <!-- Json：只读高亮；Text：可编辑 -->
            <pre v-if="format === 'json' && parsedJson" class="json-view mono" v-html="highlightJson(parsedJson)" />
            <n-input v-else v-model:value="editText" type="textarea"
              :rows="16" :input-props="{ spellcheck: false }" class="mono" />

            <!-- TTL / 删除 / 保存 -->
            <div class="detail-actions">
              <span>TTL(秒)</span>
              <n-input-number v-model:value="editTtl" size="small" :min="1" style="width: 130px"
                placeholder="留空=清除" />
              <n-button size="small" @click="applyTtl">应用 TTL</n-button>
              <div style="flex: 1" />
              <countdown-confirm label="Delete" :target="detail.key" :seconds="5" @confirm="deleteKey" />
              <n-button size="small" type="primary" :loading="saving" @click="confirmShow = true">Save</n-button>
            </div>
          </template>
          <div v-else style="text-align: center; color: #999; padding: 60px 0">
            点击左侧 Key 查看详情
          </div>
        </n-spin>
      </n-card>
    </div>

    <!-- 保存确认对话框（PRD §11.4） -->
    <n-modal v-model:show="confirmShow" preset="card" title="确认保存" style="width: 520px">
      <p>写入 Key：<b class="mono">{{ detail?.key }}</b></p>
      <p>变更摘要：</p>
      <pre class="summary mono">{{ changeSummary }}</pre>
      <template #footer>
        <div style="display: flex; justify-content: end; gap: 8px">
          <n-button size="small" @click="confirmShow = false">取消</n-button>
          <n-button size="small" type="primary" :loading="saving" @click="saveValue">确认写入</n-button>
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
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.detail-key {
  font-size: 13px;
  word-break: break-all;
}
.detail-meta {
  color: #666;
  font-size: 13px;
}
.value-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.hint {
  color: #999;
  font-size: 12px;
}
.json-view {
  background: #fafbfc;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.5;
  max-height: calc(100vh - 420px);
  overflow: auto;
  margin: 0;
  white-space: pre;
}
.detail-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.metric {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  font-size: 13px;
  color: #666;
  cursor: help;
  border-bottom: 1px dashed #d0d3d8;
  padding-bottom: 1px;
}
.metric b {
  color: #1f2329;
}
.summary {
  background: #f5f6f8;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

<style>
/* 树节点：文件夹与叶子样式统一（RedisDesktop 风格），仅计数弱化 */
.tree-label {
  font-size: 13px;
}
.tree-count {
  color: #999;
  font-size: 12px;
  margin-left: 6px;
}
/* JSON 语法高亮配色（对齐 RedisDesktop：key 蓝 / string 绿 / number 红 / bool 橙） */
.json-view .jkey {
  color: #0b63ce;
}
.json-view .jstr {
  color: #237804;
}
.json-view .jnum {
  color: #cf1322;
}
.json-view .jbool {
  color: #d46b08;
}
</style>
