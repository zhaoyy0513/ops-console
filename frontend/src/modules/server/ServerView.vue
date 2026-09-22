<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NButton,
  NCard,
  NSelect,
  NSpace,
  NTable,
  useMessage,
} from 'naive-ui'
import BaseChart from '../../components/BaseChart.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples, type SamplePoint } from '../overview/api'
import { serverApi, type ProcessRow, type ServerMetrics } from './api'

const siteStore = useSiteStore()
const message = useMessage()

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

async function load() {
  if (!siteStore.currentSiteId || !serverId.value) {
    metrics.value = null
    processes.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [m, p] = await Promise.all([
      serverApi.metrics(siteStore.currentSiteId, serverId.value),
      serverApi.processes(siteStore.currentSiteId, serverId.value).catch(() => []),
    ])
    metrics.value = m
    processes.value = p
    // 趋势（读取时采样，5s 轮询 = 5s 一个点）
    const rid = `server:${serverId.value}`
    getSamples(rid, 'cpu').then((s) => (cpuSeries.value = [...s].reverse())).catch(() => {})
    getSamples(rid, 'mem').then((s) => (memSeries.value = [...s].reverse())).catch(() => {})
  } catch (e) {
    metrics.value = null // 展示 Unknown（PRD §10：错误展示）
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

// 5s 前端轮询（页面在场才轮询；PRD 无 WebSocket 决策下的实时方案）
let pollTimer: number | null = null
onMounted(() => {
  loadServers()
  pollTimer = window.setInterval(() => {
    if (!loading.value && serverId.value) load()
  }, 5000)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
watch(() => siteStore.currentSiteId, () => {
  serverId.value = null
  loadServers()
})
watch(serverId, load)

const memPct = computed(() => {
  const m = metrics.value?.memory
  return m?.total && m?.used != null ? Math.round((m.used / m.total) * 100) : null
})

const trendOption = computed(() => {
  const labels = cpuSeries.value.map((p) => new Date(p.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
  const memPoints = memSeries.value.map((p) => p.v)
  return {
    grid: { left: 44, right: 16, top: 36, bottom: 26 },
    legend: { data: ['CPU %', '内存 %'], top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: 'CPU %', type: 'line', smooth: true, showSymbol: false, data: cpuSeries.value.map((p) => p.v), itemStyle: { color: '#0b63ce' } },
      { name: '内存 %', type: 'line', smooth: true, showSymbol: false, data: memPoints, itemStyle: { color: '#d46b08' } },
    ],
  }
})

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
        <span>服务器</span>
        <n-select
          v-model:value="serverId"
          size="small"
          style="width: 240px"
          placeholder="选择服务器"
          :options="servers"
        />
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
        <!-- 已存资源的行级测试需 per-resource test 端点（PRD §18 POST .../test），落地后补 -->
        <status-badge v-if="metrics" :status="metrics.diagnosis?.status" />
      </n-space>
    </n-card>

    <n-card v-if="error" size="small" title="查询失败">
      {{ error }}（外部系统异常不影响平台其他功能）
    </n-card>

    <template v-if="metrics">
      <n-card v-if="metrics.diagnosis?.issues?.length" size="small" title="诊断问题">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>级别</th><th>类型</th><th>当前值</th><th>阈值</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="issue in metrics.diagnosis.issues" :key="issue.type + issue.value">
              <td><status-badge :status="issue.severity" /></td>
              <td>{{ issue.type }}</td>
              <td>{{ issue.value }}</td>
              <td>{{ issue.threshold }}</td>
              <td>{{ issue.message }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <!-- 指标卡在前，趋势图全宽在后 -->
      <n-space :size="12">
        <n-card size="small" title="CPU" style="flex: 1">
          <div class="metric-big" :style="{ color: pctColor(metrics.cpu.usage) }">
            {{ metrics.cpu.usage ?? '?' }}<span class="unit">%</span>
          </div>
          <div class="metric-sub">
            {{ metrics.cpu.cores ?? '?' }} cores · iowait {{ metrics.cpu.iowait ?? '?' }}% ·
            load {{ metrics.load.load1 ?? '?' }} / {{ metrics.load.load5 ?? '?' }} / {{ metrics.load.load15 ?? '?' }}
          </div>
        </n-card>
        <n-card size="small" title="内存" style="flex: 1">
          <div class="metric-big" :style="{ color: pctColor(memPct) }">
            {{ memPct ?? '?' }}<span class="unit">%</span>
          </div>
          <div class="metric-sub">
            used {{ metrics.memory.used ?? '?' }}MB / total {{ metrics.memory.total ?? '?' }}MB ·
            avail {{ metrics.memory.available ?? '?' }}MB · swap {{ metrics.memory.swap_used ?? 0 }}MB
          </div>
        </n-card>
        <n-card size="small" title="网络" style="flex: 1">
          <div class="metric-big">
            {{ fmtBytes(metrics.network.rx) }}<span class="unit">↓</span>
            {{ fmtBytes(metrics.network.tx) }}<span class="unit">↑</span>
          </div>
          <div class="metric-sub">
            errors {{ metrics.network.errors }} · dropped {{ metrics.network.dropped }}
          </div>
        </n-card>
      </n-space>

      <n-card size="small" title="CPU / 内存趋势（5s 轮询采样）" style="width: 100%">
        <base-chart v-if="cpuSeries.length" :option="trendOption" height="220px" />
        <div v-else style="color: #999; font-size: 12px; padding: 12px 0; text-align: center">
          采样收集中，几秒后出现趋势线
        </div>
      </n-card>

      <n-card size="small" title="磁盘">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>挂载点</th><th>容量</th><th>已用</th><th>可用</th><th>使用率</th><th>Inode</th></tr>
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

      <n-card size="small" title="Top 进程">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>PID</th><th>CPU %</th><th>MEM %</th><th>命令</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in processes" :key="p.pid">
              <td>{{ p.pid }}</td>
              <td :style="{ color: pctColor(p.cpu_percent) }">{{ p.cpu_percent }}</td>
              <td>{{ p.mem_percent }}</td>
              <td class="cmd">{{ p.command }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </template>

    <n-card v-else-if="!error && !loading" size="small">
      <span style="color: #999">该站点暂无服务器配置，请在「站点管理 → 资源」中添加</span>
    </n-card>
  </n-space>
</template>

<style scoped>
.metric-big {
  font-size: 34px;
  font-weight: 600;
  line-height: 1.2;
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
