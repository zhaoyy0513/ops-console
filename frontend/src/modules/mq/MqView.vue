<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NInput, NSelect, NSpace, NSpin, NTable, NTag, useMessage } from 'naive-ui'
import BaseChart from '../../components/BaseChart.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples } from '../overview/api'
import { mqApi, type AddressRow, type MqOverview, type QueueRow } from './api'

const siteStore = useSiteStore()
const message = useMessage()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const overview = ref<MqOverview | null>(null)
const queues = ref<QueueRow[]>([])
const addresses = ref<AddressRow[]>([])
const loading = ref(false) // 首次加载（转圈而非白屏）
const heapSeries = ref<Array<{ ts: number; v: number }>>([])

async function loadInstances() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'mq')
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
  try {
    const [o, q, a] = await Promise.all([
      mqApi.overview(siteId, instanceId.value),
      mqApi.queues(siteId, instanceId.value).catch(() => [] as QueueRow[]),
      mqApi.addresses(siteId, instanceId.value).catch(() => [] as AddressRow[]),
    ])
    overview.value = o
    queues.value = q
    addresses.value = a
    // heap 趋势（后台每次真实读取时采样，60s 一个点）
    getSamples(instanceId.value, 'heap').then((s) => (heapSeries.value = [...s].reverse())).catch(() => {})
  } catch (e) {
    overview.value = null
    queues.value = []
    addresses.value = []
    message.error((e as Error).message)
  }
}

onMounted(loadInstances)
watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  overview.value = null
  loadInstances()
})
watch(instanceId, load)

// ---------- 队列模糊搜索（客户端过滤，忽略大小写） ----------
const queueFilter = ref('')
const filteredQueues = computed(() => {
  const needle = queueFilter.value.trim().toLowerCase()
  if (!needle) return queues.value
  return queues.value.filter((q) => (q.name ?? '').toLowerCase().includes(needle))
})

// ---------- 图表 ----------
const heapPct = computed(() => {
  const j = overview.value?.jvm
  if (!j?.heap_used || !j?.heap_max) return null
  return Math.round((j.heap_used / j.heap_max) * 100)
})

const heapOption = computed(() => ({
  grid: { left: 60, right: 20, top: 30, bottom: 28 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: heapSeries.value.map((p) => new Date(p.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
  },
  yAxis: {
    type: 'value',
    axisLabel: { formatter: (v: number) => `${Math.round(v / 1024 / 1024)}M` },
  },
  series: [{
    name: 'Heap',
    type: 'line',
    data: heapSeries.value.map((p) => p.v),
    smooth: true,
    showSymbol: false,
    areaStyle: { opacity: 0.15 },
    lineStyle: { color: '#0b63ce' },
    itemStyle: { color: '#0b63ce' },
  }],
}))

const topQueuesOption = computed(() => {
  const top = [...queues.value]
    .filter((q) => typeof q.message_count === 'number' && q.message_count > 0)
    .sort((a, b) => (b.message_count ?? 0) - (a.message_count ?? 0))
    .slice(0, 10)
  return {
    grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: top.map((q) => q.name),
      axisLabel: {
        width: 180,
        overflow: 'truncate',
        formatter: (v: string) => (v.length > 24 ? `${v.slice(0, 24)}…` : v),
      },
    },
    series: [{
      name: '消息数',
      type: 'bar',
      data: top.map((q) => q.message_count),
      itemStyle: { color: '#0b63ce' },
      label: { show: true, position: 'right' },
    }],
  }
})

function pctColor(pct: number | null): string {
  if (pct == null) return '#999'
  if (pct >= 90) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
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

const worstQueueStatus = computed(() => {
  const order: Record<string, number> = { CRITICAL: 3, WARNING: 2 }
  const worst = queues.value.reduce<string>(
    (acc, q) => (order[q.diagnosis?.status] ?? 0) > (order[acc] ?? 0) ? q.diagnosis.status : acc, '',
  )
  return worst || 'HEALTHY'
})
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>Broker</span>
        <n-select v-model:value="instanceId" size="small" style="width: 220px"
          placeholder="选择 Artemis" :options="instances" />
        <n-button size="small" @click="load">刷新</n-button>
        <!-- 状态标签带语义前缀，不再莫名其妙 -->
        <span v-if="overview" class="badge-line">
          Broker <status-badge :status="overview.status" />
        </span>
        <span v-if="queues.length" class="badge-line">
          队列(最差) <status-badge :status="worstQueueStatus" />
        </span>
      </n-space>
    </n-card>

    <!-- 加载态：转圈，不再白屏 -->
    <n-card v-if="loading" size="small">
      <n-spin size="medium" style="width: 100%; padding: 48px 0" />
    </n-card>

    <template v-else-if="overview">
      <n-space :size="12">
        <!-- Heap：生产 MQ 内存问题核心指标，突出显示 + 阈值着色 -->
        <n-card size="small" style="flex: 1.2" title="JVM Heap（MQ 进程内存）">
          <div class="heap-row">
            <div class="heap-big" :style="{ color: pctColor(heapPct) }">
              {{ heapPct ?? '?' }}<span class="unit">%</span>
            </div>
            <div class="heap-sub">
              <div>{{ fmtBytes(overview.jvm.heap_used) }} / {{ fmtBytes(overview.jvm.heap_max) }}</div>
              <div>NonHeap {{ fmtBytes(overview.jvm.non_heap_used) }} · 线程 {{ overview.jvm.threads ?? '-' }}</div>
              <div style="color: #999">≥80% 黄 / ≥90% 红 —— 生产"MQ 内存占满"即此处逼近上限</div>
            </div>
          </div>
        </n-card>
        <n-card size="small" style="flex: 1" title="Broker">
          <div class="kv">
            <span>版本 <b>{{ overview.version ?? '-' }}</b></span>
            <span>运行 <b>{{ overview.uptime ?? '-' }}</b></span>
            <span>连接 <b>{{ overview.connections ?? '-' }}</b></span>
            <span v-if="overview.sessions != null">会话 <b>{{ overview.sessions }}</b></span>
            <span>消费者 <b>{{ overview.consumers ?? '-' }}</b></span>
            <span>地址 <b>{{ overview.addresses ?? '-' }}</b></span>
          </div>
        </n-card>
      </n-space>

      <n-space :size="12">
        <n-card size="small" style="flex: 1" title="Heap 趋势（每分钟采样）">
          <base-chart v-if="heapSeries.length" :option="heapOption" height="220px" />
          <div v-else style="color: #999; font-size: 12px; padding: 20px 0; text-align: center">
            采样收集中，约 1 分钟后出现趋势线
          </div>
        </n-card>
        <n-card size="small" style="flex: 1" title="队列堆积 Top 10">
          <base-chart v-if="queues.length" :option="topQueuesOption" height="220px" />
          <div v-else style="color: #999; font-size: 12px; padding: 20px 0; text-align: center">无队列数据</div>
        </n-card>
      </n-space>

      <n-card size="small" title="Queues">
        <template #header-extra>
          <n-input v-model:value="queueFilter" size="small" style="width: 220px"
            placeholder="模糊搜索队列名（忽略大小写）" />
        </template>
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>Queue</th><th>状态</th><th>消息数</th><th>消费者</th>
              <th>Delivering</th><th>5 分钟前</th><th>增长</th><th>问题</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in filteredQueues" :key="q.name">
              <td class="mono" :title="q.name">{{ q.name }}</td>
              <td><status-badge :status="q.diagnosis?.status" /></td>
              <td :style="{ fontWeight: (q.message_count ?? 0) > 5000 ? 700 : 400 }">{{ q.message_count ?? '-' }}</td>
              <td>{{ q.consumer_count ?? '-' }}</td>
              <td>{{ q.delivering_count ?? '-' }}</td>
              <td>{{ q.backlog_5m_ago ?? '-' }}</td>
              <td>
                <n-tag v-if="q.growth_5m != null && q.growth_5m >= 1000" type="warning" size="small" :bordered="false">
                  +{{ q.growth_5m }}
                </n-tag>
                <span v-else>{{ q.growth_5m ?? '-' }}</span>
              </td>
              <td>{{ q.diagnosis?.issues?.map((i) => i.type).join(', ') || '-' }}</td>
            </tr>
            <tr v-if="!filteredQueues.length">
              <td colspan="8" style="text-align: center; color: #999">无匹配队列</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <n-card size="small" title="Addresses">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>Address</th><th>消息数</th><th>消费者</th><th>生产者</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in addresses" :key="a.name">
              <td class="mono">{{ a.name }}</td>
              <td>{{ a.message_count ?? '-' }}</td>
              <td>{{ a.consumer_count ?? '-' }}</td>
              <td>{{ a.producer_count ?? '-' }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </template>

    <n-card v-else-if="!loading" size="small">
      <span style="color: #999">该站点暂无 MQ 配置——请在「站点管理 → 资源 → ActiveMQ」中添加并测试连接</span>
    </n-card>
  </n-space>
</template>

<style scoped>
.badge-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 13px;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.heap-row {
  display: flex;
  align-items: center;
  gap: 20px;
}
.heap-big {
  font-size: 42px;
  font-weight: 700;
  line-height: 1;
}
.heap-big .unit {
  font-size: 16px;
  font-weight: 400;
}
.heap-sub {
  font-size: 13px;
  color: #666;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kv {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  font-size: 13px;
  color: #666;
}
.kv b {
  color: #1f2329;
}
</style>
