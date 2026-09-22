<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NTooltip,
  NTree,
  useMessage,
  type TreeOption,
} from 'naive-ui'
import { parser as jsonParser } from '@lezer/json'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import CodeJsonEditor from '../../components/CodeJsonEditor.vue'
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

async function search(reset = true) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  loading.value = true
  try {
    const page = await listKeys(siteStore.currentSiteId, instanceId.value, {
      db: db.value,
      pattern: pattern.value.trim(),
      cursor: reset ? 0 : cursor.value,
      count: 100,
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
  } catch {
    info.value = null
  }
}

function refreshDb() {
  search(true)
  loadInfo()
}

onMounted(loadInstances)
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

/** JSON 语法错误定位：lezer 解析拿错误节点位置 -> 行/列 + 附近文本（补全字段名，
 *  V8 原生错误如 'Unexpected token ",", ..."_seconds":...' 常被截断看不清字段） */
function locateJsonError(text: string): string {
  try {
    jsonParser.parse(text)
    return ''
  } catch {
    // lezer 容错解析不抛错，错误以 error 节点出现
  }
  let pos: number | null = null
  jsonParser.parse(text).iterate({
    enter: (n) => {
      if (n.type.isError && pos === null) pos = n.from
    },
  })
  if (pos === null) return 'JSON 语法错误'
  const before = text.slice(0, pos)
  const line = before.split('\n').length
  const col = pos - before.lastIndexOf('\n')
  const near = text.slice(Math.max(0, pos - 50), Math.min(text.length, pos + 50)).trim()
  return `第 ${line} 行第 ${col} 列附近有语法错误：…${near}…`
}

const jsonInvalid = computed(() => {
  if (format.value !== 'json') return null
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
    detail.value = await getKey(siteStore.currentSiteId, instanceId.value, db.value, k.key)
    const raw = toEditText(detail.value)
    format.value = isJson(raw) ? 'json' : 'text'
    editText.value = format.value === 'json'
      ? JSON.stringify(JSON.parse(raw), null, 2)
      : raw
    editTtl.value = detail.value.ttl > 0 ? detail.value.ttl : null
  } catch (e) {
    // key 已被删除/过期等：明确提示并清空右侧（不再让用户对着旧值操作）
    message.error((e as Error).message)
    clearDetail()
    search(true)
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
      editText.value = JSON.stringify(JSON.parse(editText.value), null, 2)
      format.value = 'json'
    } else {
      message.warning('当前内容不是合法 JSON，无法使用 Json 视图')
    }
  } else {
    format.value = 'text'
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
      message.error(`JSON 格式错误：${jsonInvalid.value ?? '请检查后再保存'}`)
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
        <span>DB</span>
        <n-select v-model:value="db" size="small" style="width: 160px" :options="DB_OPTIONS"
          :render-label="renderDbLabel" @update:value="refreshDb" />
        <n-input v-model:value="pattern" size="small" style="width: 240px"
          placeholder="模糊搜索，忽略大小写" @keyup.enter="refreshDb" />
        <n-button size="small" :loading="loading" @click="refreshDb">刷新</n-button>
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
            <!-- 头部：彩色类型徽标 + key + TTL/内存徽章 + 刷新 -->
            <div class="detail-head">
              <n-tag size="small" :class="`type-${detail.type}`" :bordered="false">
                {{ detail.type.toUpperCase() }}
              </n-tag>
              <span class="detail-key mono">{{ detail.key }}</span>
              <n-tag size="small" :bordered="false" round>TTL {{ fmtTtl(detail.ttl) }}</n-tag>
              <n-tag size="small" :bordered="false" round>
                内存 {{ detail.memory_usage != null ? fmtBytes(detail.memory_usage) : '?' }}
              </n-tag>
              <div style="flex: 1" />
              <n-button size="small" @click="refreshValue">刷新</n-button>
            </div>

            <!-- Text / Json：CodeMirror 高亮 + 实时校验，两种视图都可直接编辑 -->
            <div class="value-toolbar">
              <n-radio-group :value="format" size="small" @update:value="switchFormat">
                <n-radio-button value="text">Text</n-radio-button>
                <n-radio-button value="json">Json</n-radio-button>
              </n-radio-group>
              <span v-if="jsonInvalid" class="json-error">JSON 错误：{{ jsonInvalid }}</span>
              <div style="flex: 1" />
            </div>

            <code-json-editor v-if="format === 'json'" v-model="editText" height="420px" />
            <n-input v-else v-model:value="editText" type="textarea"
              :rows="16" :input-props="{ spellcheck: false }" class="mono" />

            <!-- TTL / 删除 / 保存（按钮规格统一：small 实心） -->
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
.json-error {
  color: #d03050;
  font-size: 12px;
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
</style>
