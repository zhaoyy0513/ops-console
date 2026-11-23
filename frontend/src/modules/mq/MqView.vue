<script setup lang="ts">
import { computed, h, inject, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { TooltipContent, TooltipRoot, TooltipTrigger } from '@/components/ui/tooltip'
import { message } from '@/lib/message'
import OpsDataTable from '../../components/OpsDataTable.vue'
import LoadingDots from '../../components/LoadingDots.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import EmptyState from '../../components/EmptyState.vue'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import MetricCard from '../../components/MetricCard.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples } from '../overview/api'
import { mqApi, type MqOverview, type QueueMessage, type QueueRow } from './api'
import { fmtBytes, pctColor } from '../../utils/format'

const siteStore = useSiteStore()
const messageBus = message
const { t } = useI18n()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const overview = ref<MqOverview | null>(null)
const queues = ref<QueueRow[]>([])
const loading = ref(false) // 首次加载（转圈而非白屏）
const heapSeries = ref<Array<{ ts: number; v: number }>>([])
const loadError = ref('')
const queuesError = ref('')

// ---------- 队列消息浏览（只读） ----------
const messageQueue = ref<QueueRow | null>(null)
const messageList = ref<QueueMessage[]>([])
const messageLoading = ref(false)
const messageError = ref('')

async function openMessages(q: QueueRow) {
  if (!q._mbean) return
  messageQueue.value = q
  messageList.value = []
  messageError.value = ''
  messageLoading.value = true
  try {
    messageList.value = await mqApi.browse(siteStore.currentSiteId, instanceId.value ?? '', q._mbean, q.name, 50)
  } catch (e) {
    messageError.value = (e as Error).message
  } finally {
    messageLoading.value = false
  }
}

function closeMessages() {
  messageQueue.value = null
  messageList.value = []
  messageError.value = ''
}

function fmtTimestamp(ts: number | null): string {
  if (ts == null) return '-'
  return new Date(ts).toLocaleString()
}

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
    if (toastOnFail) messageBus.error(`Broker 读取失败：${loadError.value}`)
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
    if (!silent && queuesWereOk) messageBus.error(`Queues 读取失败（显示的是上次数据）：${queuesError.value}`)
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
    messageBus.error((e as Error).message)
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

// ---------- 图表 ----------
const theme = inject<ComputedRef<'light' | 'dark'>>('opsTheme', computed(() => 'light'))
/** donut 剩余段底色：随画风三态（浅灰在黑底刺眼） */
const freeColor = computed(() => (theme.value === 'light' ? '#c1c8d0' : '#26262c'))

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
    messageBus.success(`已清空 ${q.name} 的积压消息`)
    loadHeavy()
  } catch (e) {
    messageBus.error((e as Error).message)
    throw e
  }
}

const worstQueueStatus = computed(() => {
  const order: Record<string, number> = { CRITICAL: 3, WARNING: 2 }
  const worst = queues.value.reduce<string>(
    (acc, q) => (order[q.diagnosis?.status] ?? 0) > (order[acc] ?? 0) ? q.diagnosis.status : acc, '',
  )
  return worst || 'HEALTHY'
})

// ---------- 队列表（TanStack duck-type 列；排序/空态由 OpsDataTable 承担） ----------
const queueColumns = computed<any[]>(() => [
  {
    accessorKey: 'name',
    header: t('mq.queueCol'),
    cell: (ctx: any) => {
      const q: QueueRow = ctx.row.original
      return h('span', { class: 'block max-w-[320px] truncate font-mono', title: q.name }, q.name)
    },
  },
  {
    accessorKey: 'address',
    header: t('mq.addressCol'),
    enableSorting: false,
    cell: (ctx: any) => {
      const q: QueueRow = ctx.row.original
      return h('span', { class: 'block max-w-[320px] truncate font-mono', title: q.address ?? '' }, q.address ?? '-')
    },
  },
  {
    accessorKey: 'diagnosis',
    header: t('mq.statusCol'),
    enableSorting: false,
    cell: (ctx: any) => {
      const diag = (ctx.row.original as QueueRow).diagnosis
      const tipText = diag?.issues?.length ? diag.issues.map((i) => i.message).join('；') : '诊断正常'
      return h(TooltipRoot, { delayDuration: 100 }, {
        default: () => [
          h(TooltipTrigger, { asChild: true }, {
            default: () => h('span', { class: 'inline-flex cursor-help border-b border-dashed border-border pb-px' },
              h(StatusBadge, { status: diag?.status })),
          }),
          h(TooltipContent, { class: 'max-w-80' }, { default: () => tipText }),
        ],
      })
    },
  },
  {
    accessorKey: 'message_count',
    header: t('mq.messagesCol'),
    cell: (ctx: any) => {
      const v = (ctx.row.original as QueueRow).message_count
      return h('span', { class: (v ?? 0) > 5000 ? 'font-bold' : undefined }, v ?? '-')
    },
  },
  {
    id: 'first_message_age_ms',
    accessorFn: (q: QueueRow) => q.first_message_age_ms ?? undefined,
    header: t('mq.firstMsgAgeCol'),
    // null → undefined：sortUndefined 'last' 让缺失值在正/反排序时都沉底
    sortUndefined: 'last',
    sortFn: (a: any, b: any) =>
      (a.getValue('first_message_age_ms') ?? 0) - (b.getValue('first_message_age_ms') ?? 0),
    cell: (ctx: any) => {
      const v = (ctx.row.original as QueueRow).first_message_age_ms
      return h('span', {
        class: 'font-mono tabular-nums text-xs',
        style: { color: ageColor(v) },
      }, fmtAge(v))
    },
  },
  {
    accessorKey: 'added_1m',
    header: t('mq.added1mCol'),
    cell: (ctx: any) => {
      const q: QueueRow = ctx.row.original
      const v = q.added_1m
      return h('span', {
        class: 'font-mono tabular-nums text-xs',
        style: { color: addedColor(q.added_1m) },
        title: t('mq.trendTip', { a1: q.added_1m ?? '-', a5: q.added_5m ?? '-' }),
      }, v == null ? '-' : v > 0 ? `+${v}` : '0')
    },
  },
  {
    accessorKey: 'consumer_count',
    header: t('mq.consumersCol'),
    cell: (ctx: any) => (ctx.row.original as QueueRow).consumer_count ?? '-',
  },
  {
    accessorKey: 'messages_added',
    header: t('mq.added'),
    cell: (ctx: any) => (ctx.row.original as QueueRow).messages_added ?? '-',
  },
  {
    accessorKey: 'actions',
    header: t('common.actions'),
    enableSorting: false,
    cell: (ctx: any) => {
      const q: QueueRow = ctx.row.original
      if (!q._mbean) return h('span', { class: 'text-muted-foreground' }, '-')
      return h('div', { class: 'flex items-center gap-1' }, [
        h(Button, {
          variant: 'outline', size: 'sm', title: t('mq.viewMessages'),
          onClick: () => openMessages(q),
        }, () => t('mq.view')),
        (q.message_count ?? 0) > 0
          ? h(CountdownConfirm, {
              label: t('mq.purge'),
              confirmText: t('mq.purge'),
              target: q.name,
              seconds: 3,
              width: '64px',
              onConfirm: () => emptyQueue(q),
            })
          : null,
      ])
    },
  },
])

// Esc / 遮罩点击不得关窗（对齐原 n-modal mask-closable=false / close-on-esc=false）

/** 队列数卡片点击 → 平滑滚动到队列表并闪一圈主色边框（1s 后移除） */
const queueCardRef = ref<ComponentPublicInstance | null>(null)
const queueFlash = ref(false)
let flashTimer: number | null = null
function scrollToQueues() {
  ;((queueCardRef.value?.$el as HTMLElement | undefined))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  queueFlash.value = true
  if (flashTimer != null) clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => (queueFlash.value = false), 1000)
}

/** 新增（吞吐）着色：有流量蓝、无流量灰 */
function addedColor(added: number | null): string {
  return added != null && added > 0 ? '#2080f0' : 'var(--ops-text-3)'
}

/** 最老消息滞留时长：45s / 12m / 3h / 2d */
function fmtAge(ms: number | null): string {
  if (ms == null) return '-'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h` : `${Math.floor(h / 24)}d`
}

/** 滞留着色：>30 分钟红、>5 分钟黄（与 pctColor 同一色板） */
function ageColor(ms: number | null): string | undefined {
  if (ms == null) return undefined
  if (ms > 30 * 60_000) return '#d03050'
  if (ms > 5 * 60_000) return '#f0a020'
  return undefined
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card>
      <CardContent class="flex flex-wrap items-center gap-3">
        <span>{{ $t('mq.broker') }}</span>
        <div class="w-56">
          <Select :model-value="instanceId ?? ''" @update:model-value="instanceId = String($event)">
            <SelectTrigger :placeholder="$t('mq.instance')" />
            <SelectContent>
              <SelectItem v-for="opt in instances" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" @click="load">{{ $t('common.refresh') }}</Button>
        <tab-help topic="mq" />
        <span class="poll-note">{{ $t('mq.refreshNote') }}</span>
        <span v-if="overview" class="badge-line">{{ $t('mq.brokerStatus') }} <status-badge :status="overview.status" /></span>
        <span v-if="queues.length" class="badge-line">{{ $t('mq.worstQueueCol') }} <status-badge :status="worstQueueStatus" /></span>
      </CardContent>
    </Card>

    <!-- 首载骨架：避免白屏，数据到达后整块替换 -->
    <Card v-if="loading">
      <CardContent class="flex justify-center py-12">
        <loading-dots :text="$t('common.loading')" />
      </CardContent>
    </Card>

    <Card v-else-if="loadError && !overview">
      <CardContent>
        <span class="text-sm text-destructive">Broker 读取失败：{{ loadError }}</span>
      </CardContent>
    </Card>

    <template v-else-if="overview">
      <div class="row">
        <Card class="grow-1">
          <CardHeader><CardTitle>{{ $t('mq.addrMemTitle') }}</CardTitle></CardHeader>
          <CardContent>
            <base-chart v-if="addrMemPie" :option="addrMemPie" height="220px" />
            <div v-else class="py-10 text-center text-xs text-muted-foreground">
              {{ $t('mq.noGlobalMax') }}
            </div>
            <div class="mt-1 text-center text-[13px] text-muted-foreground">
              {{ $t('mq.addrMemLine', { used: fmtBytes(overview?.address_memory_usage), max: fmtBytes(overview?.global_max_size) }) }}
              <b v-if="addrMemPct != null">（{{ addrMemPct }}%）</b>
            </div>
          </CardContent>
        </Card>
        <Card class="grow-1">
          <CardHeader><CardTitle>{{ $t('mq.heapDistTitle') }}</CardTitle></CardHeader>
          <CardContent>
            <base-chart :option="heapPieOption" height="220px" />
            <div class="mt-1 text-center text-[13px] text-muted-foreground">
              {{ $t('mq.heapLine', { used: fmtBytes(overview?.jvm?.heap_used), max: fmtBytes(overview?.jvm?.heap_max) }) }}
              <b v-if="heapPct != null">（{{ heapPct }}%）</b>
            </div>
          </CardContent>
        </Card>
        <Card class="grow-1">
          <CardHeader><CardTitle>{{ $t('mq.broker') }}</CardTitle></CardHeader>
          <CardContent>
            <div class="mc-grid">
              <metric-card :title="$t('mq.connectionsCol')" :value="overview.connections" />
              <!-- Artemis 2.19 不上报 SessionCount（恒 null 只能显示 ?），
                   换队列数：与下方队列表同源同值（3s 轮询）；点击滚动到队列表 -->
              <metric-card class="tile-click" hoverable :title="$t('mq.queuesCount')" :value="queues.length"
                @click="scrollToQueues" />
              <metric-card :title="$t('mq.consumersCol')" :value="overview.consumers" />
            </div>
            <div class="kv">
              <span>{{ $t('mq.versionCol') }} <b>{{ overview.version ?? '-' }}</b></span>
              <span>{{ $t('mq.uptimeCol') }} <b>{{ overview.uptime ?? '-' }}</b></span>
              <span>{{ $t('mq.nonHeap') }} <b>{{ fmtBytes(overview.jvm.non_heap_used) }}</b></span>
              <span>{{ $t('mq.threads') }} <b>{{ overview.jvm.threads ?? '-' }}</b></span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div class="row">
        <Card class="grow-1">
          <CardHeader><CardTitle>{{ $t('mq.heapTrend') }}</CardTitle></CardHeader>
          <CardContent>
            <base-chart v-if="heapSeries.length" :option="heapOption" height="300px" />
            <div v-else class="py-10 text-center text-xs text-muted-foreground">
              采样收集中，几秒后出现趋势线
            </div>
          </CardContent>
        </Card>
        <Card class="grow-1">
          <CardHeader><CardTitle>{{ $t('mq.topQueues') }}</CardTitle></CardHeader>
          <CardContent>
            <base-chart v-if="queues.length" :option="topQueuesOption" height="300px" />
            <div v-else class="py-10 text-center text-xs text-muted-foreground">无队列数据</div>
          </CardContent>
        </Card>
      </div>

      <Card ref="queueCardRef" :class="['grow-1', { 'flash-ring': queueFlash }]">
        <CardHeader>
          <CardTitle>{{ $t('mq.queues') }}</CardTitle>
          <template #action>
            <Input v-model="queueFilter" class="w-60 min-w-0" :placeholder="$t('mq.search')" />
          </template>
        </CardHeader>
        <CardContent>
          <div v-if="queuesError" class="pane-error">Queues 读取失败：{{ queuesError }}（每 3s 自动重试）</div>
          <OpsDataTable :columns="queueColumns" :data="filteredQueues" row-key="name">
            <template #empty><EmptyState :title="$t('mq.noMatch')" /></template>
          </OpsDataTable>
        </CardContent>
      </Card>

    </template>

    <Card v-else-if="!loading">
      <CardContent>
        <span class="text-sm text-muted-foreground">该站点暂无 MQ 配置——请在「站点管理 → 资源 → ActiveMQ」中添加并测试连接</span>
      </CardContent>
    </Card>

    <!-- 队列消息浏览：Artemis 2.19 只返回元数据 + 业务属性，不含消息正文 -->
    <Dialog :open="messageQueue !== null" @update:open="(v) => { if (!v) closeMessages() }">
      <DialogContent class="w-[860px] max-w-[94vw]">
        <DialogHeader>
          <DialogTitle>{{ $t('mq.messagesTitle', { queue: messageQueue?.name ?? '' }) }}</DialogTitle>
        </DialogHeader>
        <p class="text-xs text-muted-foreground">{{ $t('mq.messageMetaNote') }}</p>
        <div v-if="messageLoading" class="flex justify-center py-8">
          <span class="inline-block size-5 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
        </div>
        <div v-else-if="messageError" class="text-sm text-destructive">{{ messageError }}</div>
        <div v-else-if="!messageList.length" class="py-8 text-center text-sm text-muted-foreground">
          {{ $t('mq.noMessages') }}
        </div>
        <div v-else class="msg-list">
          <div v-for="m in messageList" :key="String(m.message_id)" class="msg-row">
            <div class="msg-head">
              <span class="font-mono text-xs"># {{ m.message_id ?? '-' }}</span>
              <span class="text-xs text-muted-foreground">{{ $t('mq.priority') }} {{ m.priority ?? '-' }}</span>
              <span class="text-xs text-muted-foreground">{{ fmtTimestamp(m.timestamp) }}</span>
              <span class="text-xs text-muted-foreground">{{ m.durable ? $t('mq.durable') : $t('mq.nonDurable') }}</span>
            </div>
            <pre class="msg-props">{{ JSON.stringify(m.properties, null, 2) }}</pre>
            <template v-if="m.body">
              <div class="msg-body-label">{{ $t('mq.body') }}</div>
              <pre class="msg-body">{{ m.body }}</pre>
            </template>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" :disabled="messageLoading" @click="openMessages(messageQueue!)">
            {{ $t('common.refresh') }}
          </Button>
          <Button size="sm" @click="closeMessages">{{ $t('common.close') }}</Button>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
/* 卡片行布局：原生 flex（窄屏换行堆叠），卡片最小 320px */
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
.badge-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ops-text-2);
  font-size: 13px;
  white-space: nowrap;
}
/* 工具栏刷新频率说明（与 Server 页同款） */
.poll-note {
  color: var(--ops-text-3);
  font-size: 12px;
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
.pane-error {
  color: var(--destructive);
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
.msg-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 60vh;
  overflow-y: auto;
}
.msg-row {
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-s);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.msg-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
}
.msg-props {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  padding: 8px;
  border-radius: var(--ops-radius-s);
  background: var(--ops-surface-2);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.msg-body-label {
  font-size: 11px;
  color: var(--ops-text-3);
}
.msg-body {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 8px;
  border-radius: var(--ops-radius-s);
  background: var(--ops-surface-2);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
