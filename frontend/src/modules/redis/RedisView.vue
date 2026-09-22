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
import CountdownConfirm from '../../components/CountdownConfirm.vue'
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

// ---------- 实例 / DB / 搜索状态 ----------
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
    keys.value = reset ? page.keys : [...keys.value, ...page.keys] // Load More 追加
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
    info.value = null // Unknown 态，不阻塞浏览
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
  loadInstances()
})
watch(instanceId, () => (search(true), loadInfo()))

// ---------- 树形分组（RedisDesktop 风格：按 ':' 分层折叠 + 自然排序） ----------

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
        container.push({ key: `L:${item.key}`, label: part, dir: false, item })
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

// 结构兼容 TreeOption（key/label/children 同名字段），断言绕开递归类型差异
const treeData = computed(() => buildTree(keys.value) as unknown as TreeOption[])

function renderLabel({ option }: { option: TreeOption }) {
  const node = option as unknown as TreeNode
  if (node.dir) {
    return h('span', { class: 'tree-dir' }, [
      h('span', null, node.label),
      h('span', { class: 'tree-count' }, ` (${node.count})`),
    ])
  }
  return h('span', { title: node.item.key, class: 'tree-leaf' }, [
    h(NTag, { size: 'tiny', bordered: false, style: 'margin-right: 6px' }, { default: () => node.item.type }),
    h('span', null, node.label),
  ])
}

function onTreeSelect(_keys: Array<string>, options: Array<unknown>) {
  const option = options?.[0] as unknown as TreeNode | null
  if (option && !option.dir) openKey(option.item)
}

// ---------- 详情 / 编辑（PRD §11.4/§11.5） ----------
const detail = ref<KeyDetail | null>(null)
const detailShow = ref(false)
const editText = ref('')
const editTtl = ref<number | null>(null)
const saving = ref(false)
const confirmShow = ref(false)

/** value -> 可编辑文本（RedisDesktop 风格：string 原文，其余 JSON） */
function toEditText(d: KeyDetail): string {
  const v = d.value
  if (d.type === 'string') return String(v ?? '')
  if (d.type === 'zset') return JSON.stringify(v ?? [], null, 2)
  return JSON.stringify(v ?? null, null, 2)
}

function parseEdit(d: KeyDetail): unknown {
  if (d.type === 'string') return editText.value
  return JSON.parse(editText.value) // 失败抛 SyntaxError -> 提示用户
}

async function openKey(k: KeyItem) {
  if (!siteStore.currentSiteId || !instanceId.value) return
  try {
    detail.value = await getKey(siteStore.currentSiteId, instanceId.value, db.value, k.key)
    editText.value = toEditText(detail.value)
    editTtl.value = detail.value.ttl > 0 ? detail.value.ttl : null
    detailShow.value = true
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function saveValue() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  let value: unknown
  try {
    value = parseEdit(d)
  } catch {
    message.error('JSON 格式错误，请检查后再保存')
    return
  }
  saving.value = true
  try {
    await operate(siteStore.currentSiteId, instanceId.value, {
      op: 'set', db: db.value, key: d.key, type: d.type, value,
    })
    message.success('已保存')
    confirmShow.value = false
    detailShow.value = false
    loadInfo()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

const changeSummary = computed(() => {
  const d = detail.value
  if (!d) return ''
  const preview = editText.value.length > 160 ? `${editText.value.slice(0, 160)}…` : editText.value
  return `${d.type.toUpperCase()} · ${editText.value.length} chars\n${preview}`
})

async function deleteKey() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  await operate(siteStore.currentSiteId, instanceId.value, {
    op: 'delete', db: db.value, key: d.key,
  })
  message.success(`已删除 ${d.key}`)
  detailShow.value = false
  search(true)
  loadInfo()
}

async function applyTtl() {
  const d = detail.value
  if (!d || !siteStore.currentSiteId || !instanceId.value) return
  await operate(siteStore.currentSiteId, instanceId.value, {
    op: 'expire', db: db.value, key: d.key, ttl: editTtl.value ?? -1, // null/0 以下 = PERSIST
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

    <n-card size="small" title="Keys（按前缀分层）">
      <template #header-extra>
        <span style="color: #999; font-size: 12px">{{ keys.length }} 条已加载 · 点击 key 查看详情</span>
      </template>
      <n-spin :show="loading">
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
        <div v-else style="text-align: center; color: #999; padding: 16px 0">无匹配 Key</div>
      </n-spin>
      <div v-if="cursor !== 0" style="text-align: center; margin-top: 8px">
        <n-button size="small" :loading="loading" @click="search(false)">Load More</n-button>
      </div>
    </n-card>

    <!-- Key 详情 + 编辑 -->
    <n-modal v-model:show="detailShow" preset="card"
      :title="`Key · ${detail?.key ?? ''}`" style="width: 720px">
      <template v-if="detail">
        <n-space :size="16" style="margin-bottom: 12px">
          <n-tag size="small">{{ detail.type.toUpperCase() }}</n-tag>
          <span>TTL: <b>{{ fmtTtl(detail.ttl) }}</b></span>
          <span>内存: <b>{{ detail.memory_usage != null ? fmtBytes(detail.memory_usage) : '?' }}</b></span>
        </n-space>

        <n-input v-model:value="editText" type="textarea"
          :rows="detail.type === 'string' ? 8 : 10"
          :input-props="{ spellcheck: false }"
          style="font-family: ui-monospace, monospace" />

        <n-space align="center" :size="12" style="margin-top: 12px">
          <span>TTL(秒)</span>
          <n-input-number v-model:value="editTtl" size="small" :min="1" style="width: 130px"
            placeholder="留空=清除" />
          <n-button size="small" @click="applyTtl">应用 TTL</n-button>
          <div style="flex: 1" />
          <!-- 删除：5 秒倒计时二次确认（PRD §11.5） -->
          <countdown-confirm label="Delete" :target="detail.key" :seconds="5" @confirm="deleteKey" />
          <!-- 保存：先确认（显示 key 与变更摘要），再写入（PRD §11.4 保存流程） -->
          <n-button size="small" type="primary" @click="confirmShow = true">Save</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 保存确认对话框 -->
    <n-modal v-model:show="confirmShow" preset="card" title="确认保存" style="width: 520px">
      <p>写入 Key：<b style="font-family: ui-monospace, monospace">{{ detail?.key }}</b></p>
      <p>变更摘要：</p>
      <pre class="summary">{{ changeSummary }}</pre>
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
.summary {
  background: #f5f6f8;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
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
</style>

<style>
/* 树节点样式（renderLabel 生成，非 scoped） */
.tree-dir {
  font-weight: 600;
}
.tree-count {
  color: #999;
  font-size: 12px;
  margin-left: 4px;
}
.tree-leaf {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 13px;
}
</style>
