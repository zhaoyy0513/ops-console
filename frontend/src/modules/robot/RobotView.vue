<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NSelect, NSpace, NTable, NTag, useMessage } from 'naive-ui'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { robotApi, type RobotRow } from './api'

const siteStore = useSiteStore()
const message = useMessage()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const robots = ref<RobotRow[]>([])
const loading = ref(false)
const detail = ref<RobotRow | null>(null)

// status -> StatusBadge 语义映射（robot 侧状态词与 HEALTHY/WARNING/CRITICAL 对齐）
function statusOf(r: RobotRow): string {
  const s = (r.status ?? '').toLowerCase()
  if (['error', 'fault', 'offline', 'down'].includes(s) || r.error) return 'CRITICAL'
  if (['running', 'working', 'active', 'online'].includes(s)) return 'HEALTHY'
  if (['idle', 'charging', 'standby', 'paused'].includes(s)) return 'WARNING'
  return 'UNKNOWN'
}

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

async function openDetail(r: RobotRow) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !r.id) return
  try {
    detail.value = await robotApi.detail(siteId, r.id, r.instance)
  } catch (e) {
    message.error((e as Error).message)
  }
}

onMounted(loadInstances)

// 3s 轮询（标签切走暂停，回来恢复）
let pollTimer: number | null = null
function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (instanceId.value && !document.hidden && !loading.value) load()
  }, 3000)
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
  detail.value = null
  loadInstances()
})
watch(instanceId, () => {
  detail.value = null
  load()
})
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>Robot 实例</span>
        <n-select v-model:value="instanceId" size="small" style="width: 240px"
          placeholder="选择 Robot 接入实例" :options="instances" />
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
        <span style="color: #999; font-size: 12px">不同实例可配置各自的字段映射（站点管理 → 资源 → Robot）</span>
      </n-space>
    </n-card>

    <n-card size="small" title="Robots">
      <n-table :single-line="false" size="small">
        <thead>
          <tr>
            <th>状态</th><th>ID</th><th>名称</th><th>电量</th>
            <th>当前站点</th><th>任务</th><th>最后更新</th><th style="width: 80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in robots" :key="r.id ?? ''">
            <td><status-badge :status="statusOf(r)" /></td>
            <td style="font-family: ui-monospace, monospace">{{ r.id ?? '?' }}</td>
            <td>{{ r.name ?? '-' }}</td>
            <td>
              <n-tag v-if="r.battery != null" :type="Number(r.battery) < 20 ? 'error' : 'default'" size="small" :bordered="false">
                {{ r.battery }}%
              </n-tag>
              <span v-else>-</span>
            </td>
            <td>{{ r.station ?? '-' }}</td>
            <td>{{ r.task ?? '-' }}</td>
            <td>{{ r.last_update ?? '-' }}</td>
            <td><n-button size="tiny" @click="openDetail(r)">详情</n-button></td>
          </tr>
          <tr v-if="!robots.length && !loading">
            <td colspan="8" style="text-align: center; color: #999">
              {{ instanceId ? '该实例无 Robot 数据' : '暂无 Robot 实例，请在「站点管理 → 资源」中添加' }}
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <n-card v-if="detail" :title="`Robot · ${detail.id ?? ''}`" size="small">
      <n-space :size="24" style="margin-bottom: 12px">
        <status-badge :status="statusOf(detail)" />
        <n-button size="tiny" @click="detail = null">收起</n-button>
      </n-space>
      <n-table :single-line="false" size="small" style="max-width: 560px">
        <tbody>
          <tr><th style="width: 120px">Status</th><td>{{ detail.status ?? '-' }}</td></tr>
          <tr><th>Battery</th><td>{{ detail.battery ?? '-' }}{{ detail.battery != null ? '%' : '' }}</td></tr>
          <tr><th>Position</th><td>{{ detail.station ?? '-' }}</td></tr>
          <tr><th>Task</th><td>{{ detail.task ?? '-' }}</td></tr>
          <tr><th>Error</th><td :style="{ color: detail.error ? '#d03050' : undefined }">{{ detail.error ?? '-' }}</td></tr>
        </tbody>
      </n-table>
    </n-card>
  </n-space>
</template>
