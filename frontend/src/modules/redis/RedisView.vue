<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTable,
  NTag,
  useMessage,
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
const pattern = ref('*')
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
      pattern: pattern.value || '*',
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

/** 编辑文本 -> 后端 value 结构（类型化校验在后端兜底） */
function parseEdit(d: KeyDetail): unknown {
  if (d.type === 'string') return editText.value
  return JSON.parse(editText.value) // 失败抛 SyntaxError -> 提示用户
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
        <n-input v-model:value="pattern" size="small" style="width: 220px"
          placeholder="Pattern，如 robot:*" @keyup.enter="doSearch" />
        <n-select v-model:value="typeFilter" size="small" style="width: 130px"
          :options="typeOptions" @update:value="doSearch" />
        <n-button size="small" :loading="loading" @click="doSearch">搜索</n-button>
      </n-space>
    </n-card>

    <n-card v-if="info" size="small">
      <n-space :size="24">
        <span>版本 <b>{{ info.version ?? '?' }}</b></span>
        <span>内存 <b>{{ fmtBytes(info.memory_used) }}</b> / peak {{ fmtBytes(info.memory_peak) }}</span>
        <span>客户端 <b>{{ info.connected_clients }}</b></span>
        <span>命中率 <b>{{ info.hit_rate ?? '?' }}%</b></span>
        <span>Keys(DB{{ db }}) <b>{{ info.db_size }}</b></span>
        <span>碎片率 <b>{{ info.memory_fragmentation ?? '?' }}</b></span>
      </n-space>
    </n-card>

    <n-card size="small" title="Keys">
      <template #header-extra>
        <span style="color: #999; font-size: 12px">SCAN 分页 · {{ keys.length }} 条已加载</span>
      </template>
      <n-spin :show="loading">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>Key</th><th style="width: 110px">类型</th><th style="width: 90px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="k in keys" :key="k.key">
              <td style="font-family: ui-monospace, monospace">{{ k.key }}</td>
              <td><n-tag size="small" :bordered="false">{{ k.type }}</n-tag></td>
              <td><n-button size="tiny" @click="openKey(k)">查看</n-button></td>
            </tr>
            <tr v-if="!keys.length && !loading">
              <td colspan="3" style="text-align: center; color: #999">无匹配 Key</td>
            </tr>
          </tbody>
        </n-table>
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
</style>
