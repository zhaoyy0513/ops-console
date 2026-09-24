<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NModal, NSelect, NSpace, NTable, NTag, useMessage } from 'naive-ui'
import { useSiteStore } from '../../stores/site'
import { ROBOT_FIELDS } from './fields'
import TabHelp from '../../components/TabHelp.vue'
import { robotApi, type RobotRow } from './api'

const siteStore = useSiteStore()
const message = useMessage()

const REFRESH_SECONDS = 30

/** 状态徽标语义映射（robot 侧状态词 -> 红绿灯） */
function statusTagType(r: RobotRow): 'success' | 'warning' | 'error' | 'default' {
  const s = String(r.status ?? '').toLowerCase()
  if (['error', 'fault', 'offline', 'down'].includes(s) || r.error) return 'error'
  if (['running', 'working', 'active', 'online'].includes(s)) return 'success'
  if (['idle', 'charging', 'standby', 'paused'].includes(s)) return 'warning'
  return 'default'
}

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const robots = ref<RobotRow[]>([])
const loading = ref(false)
const detail = ref<RobotRow | null>(null)
const detailShow = ref(false)

async function loadInstances() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'robots')
    instances.value = list.map((r) => ({ label: r.name, value: r.id }))
    if (!instanceId.value || !list.some((r) => r.id === instanceId.value)) {
      instanceId.value = list[0]?.id ?? null
    }
    if (instanceId.value) await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value) return
  loading.value = true
  try {
    robots.value = await robotApi.list(siteId, instanceId.value)
  } catch (e) {
    robots.value = []
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function openDetail(r: RobotRow) {
  detail.value = r
  detailShow.value = true
}

// 详情展示原始接口返回的完整 JSON（_raw 由后端附带），而非 normalize 后的结构
const detailJson = computed(() => JSON.stringify((detail.value as any)?._raw ?? detail.value, null, 2))

/** ISO -> 本地 yyyy-MM-dd HH:mm:ss；非 ISO 原样展示 */
function fmtTime(v: string | null): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

onMounted(loadInstances)

// 30s 轮询（标签切走暂停，回来恢复；间隔标注在 Robots 标题旁）
let pollTimer: number | null = null
function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (instanceId.value && !document.hidden && !loading.value) load()
  }, REFRESH_SECONDS * 1000)
}
function stopPolling() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
function onVisibility() {
  if (document.hidden) stopPolling()
  else startPolling()
}
onMounted(() => {
  startPolling()
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibility)
})

watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  robots.value = []
  loadInstances()
})
watch(instanceId, load)
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>Robot 实例</span>
        <n-select v-model:value="instanceId" size="small" style="width: 240px"
          placeholder="选择 Robot 接入实例" :options="instances" />
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
        <tab-help topic="robot" />
        <span style="color: #999; font-size: 12px">不同实例可配置字段映射（站点管理 → 资源 → Robot）</span>
      </n-space>
    </n-card>

    <n-card size="small" :title="`Robots（${REFRESH_SECONDS}s auto refresh）`">
      <n-table :single-line="false" size="small">
        <thead>
          <tr>
            <!-- 表头由 robot/fields.ts 公用定义驱动（与字段映射配置同源） -->
            <th v-for="f in ROBOT_FIELDS" :key="f.key">{{ f.label }}</th>
            <th style="width: 80px">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in robots" :key="r.id ?? ''">
            <td v-for="f in ROBOT_FIELDS" :key="f.key" :class="{ mono: f.key === 'id' }">
              <template v-if="f.key === 'status'">
                <n-tag :type="statusTagType(r)" size="small" :bordered="false">{{ r.status ?? '-' }}</n-tag>
              </template>
              <template v-else-if="f.key === 'battery'">
                <n-tag v-if="r.battery != null" :type="Number(r.battery) < 20 ? 'error' : 'default'" size="small" :bordered="false">
                  {{ r.battery }}%
                </n-tag>
                <span v-else>-</span>
              </template>
              <template v-else>{{ (r as any)[f.key] ?? '-' }}</template>
            </td>
            <td><n-button size="tiny" @click="openDetail(r)">Detail</n-button></td>
          </tr>
          <tr v-if="!robots.length && !loading">
            <td :colspan="ROBOT_FIELDS.length + 1" style="text-align: center; color: #999">
              {{ instanceId ? 'No robot data for this instance' : '暂无 Robot 实例，请在「站点管理 → 资源」中添加' }}
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- 详情弹窗：基础信息 + 完整 JSON -->
    <n-modal v-model:show="detailShow" preset="card"
      :title="`Robot · ${detail?.id ?? ''}`" style="width: 640px">
      <template v-if="detail">
        <n-table :single-line="false" size="small">
          <tbody>
            <tr><th style="width: 140px">Robot Code</th><td style="font-family: ui-monospace, monospace">{{ detail.id ?? '-' }}</td></tr>
            <tr><th>Robot Name</th><td>{{ detail.name ?? '-' }}</td></tr>
            <tr><th>Battery</th><td>{{ detail.battery ?? '-' }}{{ detail.battery != null ? '%' : '' }}</td></tr>
            <tr><th>Position</th><td>{{ detail.station ?? '-' }}</td></tr>
            <tr><th>Last Update</th><td>{{ fmtTime(detail.last_update) }}</td></tr>
          </tbody>
        </n-table>
        <div style="margin: 14px 0 6px; color: #666; font-size: 13px">Raw JSON</div>
        <pre class="detail-json">{{ detailJson }}</pre>
      </template>
    </n-modal>
  </n-space>
</template>

<style scoped>
.detail-json {
  background: #fafbfc;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 12px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 300px;
  overflow: auto;
  margin: 0;
  white-space: pre;
}
</style>
