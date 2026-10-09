<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCard, NInput, NModal, NSelect, NSpace, NSpin, NTable, NTooltip, useMessage } from 'naive-ui'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import EmptyState from '../../components/EmptyState.vue'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import MetricCard from '../../components/MetricCard.vue'
import SortTh from '../../components/SortTh.vue'
import { useTableSort } from '../../composables/useTableSort'
import { useSiteStore } from '../../stores/site'
import { getSamples } from '../overview/api'
import { mqApi, type MqOverview, type QueueRow } from './api'
import { fmtBytes, pctColor } from '../../utils/format'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const overview = ref<MqOverview | null>(null)
const queues = ref<QueueRow[]>([])
const loading = ref(false) // 首次加载（转圈而非白屏）
const heapSeries = ref<Array<{ ts: number; v: number }>>([])
const loadError = ref('')
const queuesError = ref('')

/** 轮询：overview/heap/queues 均随 3s tick 刷新（queues 有后端 5s 缓存兜底） */
async function loadLight(toastOnFail = false) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value) return
  try {
    const o = await mqApi.overview(siteId, instanceId.value)
    overview.value = o
    loadError.value = ''
    getSamples(`mq:${siteId}:${instanceId.value}`, 'heap')
      .then((s) => (heapSeries.value = [...s].reverse())).catch(() => {})
  } catch (e) {
    overview.value = null
    loadError.value = (e as Error).message
    if (toastOnFail) message.error(`Broker 读取失败：${loadError.value}`)
  }
}

let queuesWereOk = true
async function loadHeavy(silent = false) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value) return
  try {
    queues.value = await mqApi.queues(siteId, instanceId.value)
    queuesError.value = ''
    queuesWereOk = true
  } catch (e) {
    // 保留上一次成功的数据不清空；仅在 成功->失败 边缘提示一次（避免轮询 toast 轰炸）
    queuesError.value = (e as Error).message
    if (!silent && queuesWereOk) message.error(`Queues 读取失败（显示的是上次数据）：${queuesError.value}`)
    queuesWereOk = false
  }
}

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

/** 手动/首次：全量刷新（overview + queues，失败弹 toast） */
async function load() {
  await loadLight(true)
  await loadHeavy(false)
}
onMounted(loadInstances)

// 轮询：页面在场时每 3s 全量刷新（queues 由后端 CACHE_TTL 缓存保护 broker）
let pollTimer: number | null = null

function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (!instanceId.value || document.hidden) return
    loadLight()
    loadHeavy(true)
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
  if (flashTimer != null) clearTimeout(flashTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})

watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  overview.value = null
  loadInstances()
})
watch(instanceId, load)

// ---------- 搜索（匹配队列名 + 所属 Address，忽略大小写） ----------
const queueFilter = ref('')
const filteredQueues = computed(() => {
  const needle = queueFilter.value.trim().toLowerCase()
  if (!needle) return queues.value
  return queues.value.filter(
    (q) =>
      (q.name ?? '').toLowerCase().includes(needle) ||
      (q.address ?? '').toLowerCase().includes(needle),
  )
})

// ---------- 队列表当前页排序（名称/消息数/1m新增/累计新增/消费者；地址与状态列不排） ----------
const {
  sortKey: qSortKey,
  sortDir: qSortDir,
  sortedRows: sortedQueues,
  toggleSort: toggleQueueSort,
} = useTableSort<QueueRow>(filteredQueues, (q, k) => (q as unknown as Record<string, unknown>)[k])

// ---------- 图表 ----------
const opsDark = inject<{ isDark: Ref<boolean> }>('opsDark')!
/** donut 剩余段底色：随暗色切换（浅灰在黑底刺眼） */
const freeColor = computed(() => (opsDark.isDark.value ? '#26262c' : '#c1c8d0'))

const heapPct = computed(() => {
  const j = overview.value?.jvm
  // heap_used 为 0 是合法值，仅 null 视为无数据（falsy 判断会把 0 误判成缺失）
  if (j?.heap_used == null || !j?.heap_max) return null
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
  }],
}))

const topQueuesOption = computed(() => {
  const top = [...queues.value]
    .filter((q) => typeof q.message_count === 'number' && q.message_count > 0)
    .sort((a, b) => (b.message_count ?? 0) - (a.message_count ?? 0))
    .slice(0, 10)
  return {
    grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
    tooltip: {
      trigger: 'axis',
      // 悬浮展示队列名 + 所属 Address + 消息数（y 轴类目只有名字，Address 从 dataIndex 取回）
      formatter: (params: Array<{ dataIndex: number }>) => {
        const q = top[params[0]?.dataIndex]
        if (!q) return ''
        return t('mq.topQueueTip', { name: q.name, address: q.address ?? '-', count: q.message_count ?? '-' })
      },
    },
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
      label: { show: true, position: 'right' },
    }],
  }
})

const pieTooltipFormatter = (p: { name: string; value: number; percent: number }): string =>
  `${p.name}<br/>${fmtBytes(p.value)}（${p.percent}%）`

const addrMemPie = computed(() => {
  const used = overview.value?.address_memory_usage
  const max = overview.value?.global_max_size
  // 空闲时 address_memory_usage = 0 是合法值，不能 falsy 判断（否则饼图在 0 字节时消失）
  if (used == null || !max) return null
  return {
    title: {
      text: `${addrMemPct.value ?? '?'}%`,
      left: 'center',
      top: 'middle',
      textStyle: { fontSize: 22, fontWeight: 700, color: pctColor(addrMemPct.value) },
    },
    tooltip: { trigger: 'item', formatter: pieTooltipFormatter },
    series: [{
      type: 'pie',
      radius: ['55%', '80%'],
      label: { show: false },
      data: [
        { name: 'Address Memory', value: used, itemStyle: { color: '#2563eb' } },
        { name: 'Free', value: Math.max(0, max - used), itemStyle: { color: freeColor.value } },
      ],
    }],
  }
})

const addrMemPct = computed(() => {
  const u = overview.value?.address_memory_usage
  const m = overview.value?.global_max_size
  return u != null && m ? Math.round((u / m) * 100) : null
})

const heapPieOption = computed(() => {
  const j = overview.value?.jvm
  const used = j?.heap_used ?? 0
  const max = j?.heap_max ?? 1
  return {
    title: {
      text: `${heapPct.value ?? '?'}%`,
      left: 'center',
      top: 'middle',
      textStyle: { fontSize: 22, fontWeight: 700, color: pctColor(heapPct.value) },
    },
    tooltip: { trigger: 'item', formatter: pieTooltipFormatter },
    series: [{
      type: 'pie',
      radius: ['55%', '80%'],
      label: { show: false },
      data: [
        { name: 'Used', value: used, itemStyle: { color: '#f0a020' } },
        { name: 'Free', value: Math.max(0, max - used), itemStyle: { color: freeColor.value } },
      ],
    }],
  }
})

async function emptyQueue(q: QueueRow) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value || !q._mbean) return
  try {
    await mqApi.emptyQueue(siteId, instanceId.value, q._mbean, q.name)
    message.success(`已清空 ${q.name} 的积压消息`)
    loadHeavy()
  } catch (e) {
    message.error((e as Error).message)
  }
}

const worstQueueStatus = computed(() => {
  const order: Record<string, number> = { CRITICAL: 3, WARNING: 2 }
  const worst = queues.value.reduce<string>(
    (acc, q) => (order[q.diagnosis?.status] ?? 0) > (order[acc] ?? 0) ? q.diagnosis.status : acc, '',
  )
  return worst || 'HEALTHY'
})

/** 地址分布（与队列表同源）：客户端按 address 聚合，而非 broker 的 AddressCount
 *  （后者含无队列地址，导致与表格条数对不上的观感） */
const addrCount = computed(() => new Set(queues.value.map((q) => q.address).filter(Boolean)).size)
const addrBreakdown = computed(() => {
  const map = new Map<string, { address: string; count: number; msgs: number }>()
  for (const q of queues.value) {
    if (!q.address) continue
    const row = map.get(q.address) ?? { address: q.address, count: 0, msgs: 0 }
    row.count += 1
    row.msgs += q.message_count ?? 0
    map.set(q.address, row)
  }
  return [...map.values()].sort((a, b) => b.msgs - a.msgs)
})
const showAddrModal = ref(false)

/** 队列数卡片点击 → 平滑滚动到队列表并闪一圈主色边框（1s 后移除） */
const queueCardRef = ref<InstanceType<typeof NCard> | null>(null)
const queueFlash = ref(false)
let flashTimer: number | null = null
function scrollToQueues() {
  ;(queueCardRef.value?.$el as HTMLElement | undefined)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  queueFlash.value = true
  if (flashTimer != null) clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => (queueFlash.value = false), 1000)
}

/** 新增（吞吐）着色：有流量蓝、无流量灰 */
function addedColor(added: number | null): string {
  return added != null && added > 0 ? '#2080f0' : 'var(--ops-text-3)'
}
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12">
        <span>{{ $t('mq.broker') }}</span>
        <n-select v-model:value="instanceId" size="small" style="width: 220px"
          :placeholder="$t('mq.instance')" :options="instances" />
        <n-button size="small" @click="load">{{ $t("common.refresh") }}</n-button>
        <tab-help topic="mq" />
        <span class="poll-note">{{ $t('mq.refreshNote') }}</span>
        <span v-if="overview" class="badge-line">{{ $t('mq.brokerStatus') }} <status-badge :status="overview.status" /></span>
        <span v-if="queues.length" class="badge-line">{{ $t('mq.worstQueueCol') }} <status-badge :status="worstQueueStatus" /></span>
      </n-space>
    </n-card>

    <!-- 加载态：转圈，不再白屏 -->
    <n-card v-if="loading" size="small">
      <n-spin size="medium" style="width: 100%; padding: 48px 0" />
    </n-card>

    <n-card v-else-if="loadError && !overview" size="small">
      <span style="color: #d03050">Broker 读取失败：{{ loadError }}</span>
    </n-card>

    <template v-else-if="overview">
      <div class="row">
        <n-card size="small" class="grow-1" :title="$t('mq.addrMemTitle')">
          <base-chart v-if="addrMemPie" :option="addrMemPie" height="220px" />
          <div v-else style="color: #999; font-size: 12px; padding: 40px 0; text-align: center">
            {{ $t('mq.noGlobalMax') }}
          </div>
          <div style="text-align: center; color: #666; font-size: 13px; margin-top: 4px">
            {{ $t('mq.addrMemLine', { used: fmtBytes(overview?.address_memory_usage), max: fmtBytes(overview?.global_max_size) }) }}
            <b v-if="addrMemPct != null">（{{ addrMemPct }}%）</b>
          </div>
        </n-card>
        <n-card size="small" class="grow-1" :title="$t('mq.heapDistTitle')">
          <base-chart :option="heapPieOption" height="220px" />
          <div style="text-align: center; color: #666; font-size: 13px; margin-top: 4px">
            {{ $t('mq.heapLine', { used: fmtBytes(overview?.jvm?.heap_used), max: fmtBytes(overview?.jvm?.heap_max) }) }}
            <b v-if="heapPct != null">（{{ heapPct }}%）</b>
          </div>
        </n-card>
        <n-card size="small" class="grow-1" :title="$t('mq.broker')">
          <div class="mc-grid">
            <metric-card :title="$t('mq.connectionsCol')" :value="overview.connections" />
            <!-- Artemis 2.19 不上报 SessionCount（恒 null 只能显示 ?），
                 换队列数：与下方队列表同源同值（3s 轮询）；点击滚动到队列表 -->
            <metric-card class="tile-click" hoverable :title="$t('mq.queuesCount')" :value="queues.length"
              @click="scrollToQueues" />
            <metric-card :title="$t('mq.consumersCol')" :value="overview.consumers" />
            <!-- 地址数：按队列表去重地址统计（非 broker AddressCount）；点击查看地址分布 -->
            <metric-card class="tile-click" hoverable :title="$t('mq.addressesCol')" :value="addrCount"
              @click="showAddrModal = true" />
          </div>
          <div class="kv">
            <span>{{ $t('mq.versionCol') }} <b>{{ overview.version ?? '-' }}</b></span>
            <span>{{ $t('mq.uptimeCol') }} <b>{{ overview.uptime ?? '-' }}</b></span>
            <span>{{ $t('mq.nonHeap') }} <b>{{ fmtBytes(overview.jvm.non_heap_used) }}</b></span>
            <span>{{ $t('mq.threads') }} <b>{{ overview.jvm.threads ?? '-' }}</b></span>
          </div>
        </n-card>
      </div>

      <div class="row">
        <n-card size="small" class="grow-1" :title="$t('mq.heapTrend')">
          <base-chart v-if="heapSeries.length" :option="heapOption" height="300px" />
          <div v-else style="color: #999; font-size: 12px; padding: 40px 0; text-align: center">
            采样收集中，几秒后出现趋势线
          </div>
        </n-card>
        <n-card size="small" class="grow-1" :title="$t('mq.topQueues')">
          <base-chart v-if="queues.length" :option="topQueuesOption" height="300px" />
          <div v-else style="color: #999; font-size: 12px; padding: 40px 0; text-align: center">无队列数据</div>
        </n-card>
      </div>

      <n-card ref="queueCardRef" size="small" :title="$t('mq.queues')" :class="{ 'flash-ring': queueFlash }">
        <template #header-extra>
          <n-input v-model:value="queueFilter" size="small" style="width: 240px"
            :placeholder="$t('mq.search')" />
        </template>
        <div v-if="queuesError" class="pane-error">Queues 读取失败：{{ queuesError }}（每 3s 自动重试）</div>
        <div class="table-scroll">
          <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <sort-th :label="$t('mq.queueCol')" :active="qSortKey === 'name'" :dir="qSortKey === 'name' ? qSortDir : null" @sort="toggleQueueSort('name')" />
              <th>{{ $t('mq.addressCol') }}</th><th>{{ $t('mq.statusCol') }}</th>
              <sort-th :label="$t('mq.messagesCol')" :active="qSortKey === 'message_count'" :dir="qSortKey === 'message_count' ? qSortDir : null" @sort="toggleQueueSort('message_count')" />
              <sort-th style="width: 90px" :label="$t('mq.added1mCol')" :active="qSortKey === 'added_1m'" :dir="qSortKey === 'added_1m' ? qSortDir : null" @sort="toggleQueueSort('added_1m')" />
              <sort-th :label="$t('mq.consumersCol')" :active="qSortKey === 'consumer_count'" :dir="qSortKey === 'consumer_count' ? qSortDir : null" @sort="toggleQueueSort('consumer_count')" />
              <sort-th :label="$t('mq.added')" :active="qSortKey === 'messages_added'" :dir="qSortKey === 'messages_added' ? qSortDir : null" @sort="toggleQueueSort('messages_added')" />
              <th>{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in sortedQueues" :key="q.name">
              <td class="mono" :title="q.name">{{ q.name }}</td>
              <td class="mono" :title="q.address ?? ''">{{ q.address ?? '-' }}</td>
              <td>
                <n-tooltip trigger="hover" :style="{ maxWidth: '320px' }">
                  <template #trigger>
                    <span class="tip"><status-badge :status="q.diagnosis?.status" /></span>
                  </template>
                  {{ q.diagnosis?.issues?.length
                    ? q.diagnosis.issues.map((i) => i.message).join('；')
                    : '诊断正常' }}
                </n-tooltip>
              </td>
              <td :style="{ fontWeight: (q.message_count ?? 0) > 5000 ? 700 : 400 }">{{ q.message_count ?? '-' }}</td>
              <td>
                <span class="trend-num" :style="{ color: addedColor(q.added_1m) }"
                  :title="$t('mq.trendTip', { a1: q.added_1m ?? '-', a5: q.added_5m ?? '-' })">
                  {{ q.added_1m == null ? '-' : q.added_1m > 0 ? `+${q.added_1m}` : '0' }}
                </span>
              </td>
              <td>{{ q.consumer_count ?? '-' }}</td>
              <td>{{ q.messages_added ?? '-' }}</td>
              <td>
                <!-- 仅清空一个操作：只对可管理（_mbean）且有积压的队列渲染，否则灰色占位 -->
                <countdown-confirm
                  v-if="q._mbean && (q.message_count ?? 0) > 0"
                  :label="$t('mq.purge')"
                  :confirm-text="$t('mq.purge')"
                  :target="q.name"
                  :seconds="3"
                  width="64px"
                  @confirm="emptyQueue(q)"
                />
                <span v-else style="color: #999">-</span>
              </td>
            </tr>
            <tr v-if="!filteredQueues.length">
              <td :colspan="8"><EmptyState :title="$t('mq.noMatch')" /></td>
            </tr>
          </tbody>
        </n-table>
        </div>
      </n-card>

      <!-- 地址分布弹窗：客户端按队列 address 聚合，按消息合计降序 -->
      <n-modal v-model:show="showAddrModal" preset="card" :title="$t('mq.addrBreakdown')"
        style="width: 640px; max-width: 94vw" :mask-closable="false" :close-on-esc="false">
        <div v-if="addrBreakdown.length" class="table-scroll">
          <n-table :single-line="false" size="small">
            <thead>
              <tr>
                <th>{{ $t('mq.addrCol') }}</th>
                <th style="width: 90px">{{ $t('mq.addrQueueCount') }}</th>
                <th style="width: 110px">{{ $t('mq.addrMsgSum') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in addrBreakdown" :key="row.address">
                <td class="mono" :title="row.address">{{ row.address }}</td>
                <td>{{ row.count }}</td>
                <td>{{ row.msgs }}</td>
              </tr>
            </tbody>
          </n-table>
        </div>
        <EmptyState v-else :title="$t('mq.noMatch')" />
        <template #footer>
          <n-space justify="end">
            <n-button size="small" @click="showAddrModal = false">{{ $t('common.close') }}</n-button>
          </n-space>
        </template>
      </n-modal>
    </template>

    <n-card v-else-if="!loading" size="small">
      <span style="color: #999">该站点暂无 MQ 配置——请在「站点管理 → 资源 → ActiveMQ」中添加并测试连接</span>
    </n-card>
  </n-space>
</template>

<style scoped>
/* 卡片行布局：原生 flex（n-space 会塌缩子项宽度）；窄屏换行堆叠，卡片最小 320px */
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: stretch;
}
.grow-1 {
  flex: 1;
  min-width: 320px;
}
.grow-2 {
  flex: 1.4;
  min-width: 0;
}
.badge-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 13px;
  white-space: nowrap;
}
/* 工具栏刷新频率说明（与 Server 页同款） */
.poll-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
.tip {
  cursor: help;
  border-bottom: 1px dashed #d0d3d8;
  padding-bottom: 1px;
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
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--ops-text-2);
}
.kv b {
  color: var(--ops-text-1);
}
/* Broker 计数 MetricCard 网格：窄屏自动减列 */
.mc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
/* 表格内部横向滚动，不撑破页面 */
.table-scroll {
  overflow-x: auto;
}
/* 队列表新增（吞吐）列 */
.trend-num {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}
.pane-error {
  color: #d03050;
  font-size: 12px;
  margin-bottom: 8px;
}
/* 可点击 MetricCard（队列数/地址数）：与 Server 页僵尸卡同款 */
.tile-click {
  cursor: pointer;
}
/* 队列数卡片点击后队列表的 1s 主色描边 */
.flash-ring {
  border-color: var(--ops-primary);
  box-shadow: 0 0 0 2px var(--ops-primary);
  transition: box-shadow 160ms ease;
}
</style>
