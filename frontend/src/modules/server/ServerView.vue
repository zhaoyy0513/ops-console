<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCard,
  NSelect,
  NSpace,
  NTable,
  useMessage,
} from 'naive-ui'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples, type SamplePoint } from '../overview/api'
import { serverApi, type ProcessRow, type ServerMetrics } from './api'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()

const servers = ref<Array<{ label: string; value: string }>>([])
const serverId = ref<string | null>(null)
const metrics = ref<ServerMetrics | null>(null)
const processes = ref<ProcessRow[]>([])
const loading = ref(false)
const error = ref('')
const cpuSeries = ref<SamplePoint[]>([])
const memSeries = ref<SamplePoint[]>([])

// 只读原则：本页面无任何写入口（验收 8）
async function loadServers() {
  try {
    const siteId = siteStore.currentSiteId
    if (!siteId) return
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'servers')
    servers.value = list.map((s) => ({ label: s.name, value: s.id }))
    if (!serverId.value || !list.some((s) => s.id === serverId.value)) {
      serverId.value = list[0]?.id ?? null
    }
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function load(silent = false) {
  if (!siteStore.currentSiteId || !serverId.value) {
    metrics.value = null
    processes.value = []
    return
  }
  loading.value = !silent // 轮询静默更新（不转圈），手动刷新才转圈
  error.value = ''
  try {
    const [m, p] = await Promise.all([
      serverApi.metrics(siteStore.currentSiteId, serverId.value),
      serverApi.processes(siteStore.currentSiteId, serverId.value).catch(() => []),
    ])
    metrics.value = m
    processes.value = p
    // 趋势（读取时采样，3s 轮询 = 3s 一个点；rid 带站点维度）
    const rid = `server:${siteStore.currentSiteId}:${serverId.value}`
    getSamples(rid, 'cpu').then((s) => (cpuSeries.value = [...s].reverse())).catch(() => {})
    getSamples(rid, 'mem').then((s) => (memSeries.value = [...s].reverse())).catch(() => {})
  } catch (e) {
    if (!silent) {
      metrics.value = null // 展示 Unknown（PRD §10：错误展示）
      error.value = (e as Error).message
    }
  } finally {
    loading.value = false
  }
}

// 3s 前端轮询（页面在场才轮询；浏览器标签切走时暂停，回来恢复）
let pollTimer: number | null = null

function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (!loading.value && serverId.value) load(true)
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
  loadServers()
  startPolling()
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibility)
})
watch(() => siteStore.currentSiteId, () => {
  serverId.value = null
  loadServers()
})
watch(serverId, () => load(false))

const memPct = computed(() => {
  const m = metrics.value?.memory
  return m?.total && m?.used != null ? Math.round((m.used / m.total) * 100) : null
})

const trendOption = computed(() => {
  const labels = cpuSeries.value.map((p) => new Date(p.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
  const memPoints = memSeries.value.map((p) => p.v)
  return {
    grid: { left: 44, right: 16, top: 36, bottom: 26 },
    legend: { data: [t('server.cpuCol'), t('server.memCol')], top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: t('server.cpuCol'), type: 'line', smooth: true, showSymbol: false, data: cpuSeries.value.map((p) => p.v), itemStyle: { color: '#0b63ce' } },
      { name: t('server.memCol'), type: 'line', smooth: true, showSymbol: false, data: memPoints, itemStyle: { color: '#d46b08' } },
    ],
  }
})

// 环形饼图：used vs 剩余，中心大字百分比
function donutOption(pct: number | null | undefined, usedColor: string, label: string) {
  const v = pct ?? 0
  return {
    tooltip: { trigger: 'item', formatter: () => `${label}: ${pct ?? '?'}%` },
    title: {
      text: pct == null ? '?' : `${pct}%`,
      left: 'center',
      top: 'middle',
      textStyle: { fontSize: 22, fontWeight: 'bold', color: pctColor(pct) },
    },
    series: [
      {
        type: 'pie',
        radius: ['62%', '85%'],
        center: ['50%', '50%'],
        label: { show: false },
        labelLine: { show: false },
        emphasis: { disabled: true }, // hover 不淡出剩余段
        data: [
          { value: v, itemStyle: { color: usedColor } },
          { value: Math.max(0, 100 - v), itemStyle: { color: '#e5e6eb' } },
        ],
      },
    ],
  }
}

const cpuDonutOption = computed(() => donutOption(metrics.value?.cpu.usage, '#0b63ce', `${t('server.cpu')} used%`))
const memDonutOption = computed(() => donutOption(memPct.value, '#d46b08', `${t('server.memory')} used%`))

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)}${units[i]}`
}

function fmtMB(mb: number | null | undefined): string {
  if (mb == null) return '-'
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${Math.round(mb)}MB`
}

// Disk 概览卡：use_percent 最高的挂载点
const topDisk = computed(() => {
  const rows = metrics.value?.disk ?? []
  if (!rows.length) return null
  return rows.reduce((a, b) => (b.use_percent > a.use_percent ? b : a))
})

function pctColor(pct: number | null | undefined): string {
  if (pct == null) return '#999'
  if (pct >= 90) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
}
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>{{ $t('server.title') }}</span>
        <n-select
          v-model:value="serverId"
          size="small"
          style="width: 240px"
          :placeholder="$t('server.select')"
          :options="servers"
        />
        <n-button size="small" :loading="loading" @click="load(false)">{{ $t('server.refresh') }}</n-button>
        <tab-help topic="server" />
        <!-- 已存资源的行级测试需 per-resource test 端点（PRD §18 POST .../test），落地后补 -->
        <status-badge v-if="metrics" :status="metrics.diagnosis?.status" />
      </n-space>
    </n-card>

    <n-card v-if="error" size="small" :title="$t('server.queryFailed')">
      {{ error }}{{ $t('server.failedNote') }}
    </n-card>

    <template v-if="metrics">
      <n-card v-if="metrics.diagnosis?.issues?.length" size="small" :title="$t('server.issues')">
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('server.level') }}</th>
              <th>{{ $t('server.type') }}</th>
              <th>{{ $t('server.value') }}</th>
              <th>{{ $t('server.threshold') }}</th>
              <th>{{ $t('server.detail') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="issue in metrics.diagnosis.issues" :key="issue.type + issue.value">
              <td><status-badge :status="issue.severity" /></td>
              <td>{{ issue.type }}</td>
              <td>{{ issue.value }}</td>
              <td>{{ issue.threshold }}</td>
              <td>{{ $t(`server.issue_${issue.type}`, { value: issue.value, threshold: issue.threshold, mount: issue.mount ?? '-' }) }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <!-- 指标卡在前，趋势图全宽在后 -->
      <n-space :size="12">
        <n-card size="small" :title="$t('server.cpu')" style="flex: 1">
          <base-chart :option="cpuDonutOption" height="120px" />
          <div class="metric-note">{{ $t('server.thresholdNote') }}</div>
          <div class="metric-sub">
            {{ $t('server.cores') }} {{ metrics.cpu.cores ?? '?' }} · {{ $t('server.iowait') }} {{ metrics.cpu.iowait ?? '?' }}% ·
            {{ $t('server.load') }} {{ metrics.load.load1 ?? '?' }} / {{ metrics.load.load5 ?? '?' }} / {{ metrics.load.load15 ?? '?' }}
          </div>
        </n-card>
        <n-card size="small" :title="$t('server.memory')" style="flex: 1">
          <base-chart :option="memDonutOption" height="120px" />
          <div class="metric-note">{{ $t('server.thresholdNote') }}</div>
          <div class="metric-sub">
            {{ $t('server.used') }} {{ fmtMB(metrics.memory.used) }} / {{ $t('server.total') }} {{ fmtMB(metrics.memory.total) }} ·
            {{ $t('server.avail') }} {{ fmtMB(metrics.memory.available) }} · {{ $t('server.swap') }} {{ fmtMB(metrics.memory.swap_used ?? 0) }}
          </div>
        </n-card>
        <n-card size="small" :title="$t('server.network')" style="flex: 1">
          <div class="metric-big">
            {{ fmtBytes(metrics.network.rx) }}<span class="unit">↓</span>
            {{ fmtBytes(metrics.network.tx) }}<span class="unit">↑</span>
          </div>
          <div class="metric-sub">
            errors {{ metrics.network.errors }} · dropped {{ metrics.network.dropped }}
          </div>
        </n-card>
        <n-card size="small" :title="$t('server.disk')" style="flex: 1">
          <div class="metric-big" :style="{ color: pctColor(topDisk?.use_percent) }">
            {{ topDisk ? `${topDisk.use_percent}` : '?' }}<span class="unit">%</span>
          </div>
          <div class="metric-sub" v-if="topDisk">
            {{ topDisk.mount }} · {{ $t('server.used') }} {{ topDisk.used }} / {{ $t('server.total') }} {{ topDisk.size }}
          </div>
          <div class="metric-sub" v-else>-</div>
        </n-card>
      </n-space>

      <n-card size="small" :title="$t('server.trend')" style="width: 100%">
        <base-chart v-if="cpuSeries.length" :option="trendOption" height="220px" />
        <div v-else style="color: #999; font-size: 12px; padding: 12px 0; text-align: center">
          {{ $t('server.emptyMetrics') }}
        </div>
      </n-card>

      <n-card size="small" :title="$t('server.topProcesses')">
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('server.pid') }}</th>
              <th>{{ $t('server.cpuCol') }}</th>
              <th>{{ $t('server.memCol') }}</th>
              <th>{{ $t('server.command') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in processes.slice(0, 10)" :key="p.pid">
              <td>{{ p.pid }}</td>
              <td :style="{ color: pctColor(p.cpu_percent) }">{{ p.cpu_percent }}</td>
              <td>{{ p.mem_percent }}</td>
              <td class="cmd">{{ p.command }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <n-card size="small" :title="$t('server.disk')">
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('server.mount') }}</th>
              <th>{{ $t('server.size') }}</th>
              <th>{{ $t('server.usedCol') }}</th>
              <th>{{ $t('server.availCol') }}</th>
              <th>{{ $t('server.usage') }}</th>
              <th>{{ $t('server.inode') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in metrics.disk" :key="d.mount">
              <td>{{ d.mount }}</td>
              <td>{{ d.size }}</td>
              <td>{{ d.used }}</td>
              <td>{{ d.avail }}</td>
              <td :style="{ color: pctColor(d.use_percent), fontWeight: 600 }">{{ d.use_percent }}%</td>
              <td>{{ d.inode_percent ?? '-' }}%</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </template>

    <n-card v-else-if="!error && !loading" size="small">
      <span style="color: #999">{{ $t('server.noServers') }}</span>
    </n-card>
  </n-space>
</template>

<style scoped>
.metric-big {
  flex-shrink: 0;
  font-size: 34px;
  font-weight: 600;
  line-height: 1.2;
}
.metric-note {
  margin-top: 6px;
  color: #999;
  font-size: 11px;
}
.unit {
  font-size: 14px;
  font-weight: 400;
  margin-left: 4px;
  color: #999;
}
.metric-sub {
  margin-top: 6px;
  color: #666;
  font-size: 12px;
}
.cmd {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
