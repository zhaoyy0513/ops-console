<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NInput, NModal, NSelect, NSpace, NSpin, NTable, useMessage } from 'naive-ui'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import EmptyState from '../../components/EmptyState.vue'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples } from '../overview/api'
import { mqApi, type MqOverview, type QueueMessage, type QueueRow } from './api'
import { fmtBytes, pctColor } from '../../utils/format'

const siteStore = useSiteStore()
const message = useMessage()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const overview = ref<MqOverview | null>(null)
const queues = ref<QueueRow[]>([])
const loading = ref(false) // 首次加载（转圈而非白屏）
const heapSeries = ref<Array<{ ts: number; v: number }>>([])
const loadError = ref('')
const queuesError = ref('')

/** 轮询分层：overview/heap 轻量 3s；queues 响应大，15s + 手动刷新 */
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

// 轮询分层：overview/heap 轻量 3s；queues 响应大 15s 一次（页面在场才轮询）
let pollTimer: number | null = null
let heavyTick = 0

function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (!instanceId.value || document.hidden) return
    loadLight()
    if (++heavyTick % 5 === 0) loadHeavy(true)
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

const FREE_COLOR = '#c1c8d0'

function pieTooltipFormatter(p: { name: string; value: number; percent: number }): string {
  return `${p.name}<br/>${fmtBytes(p.value)}（${p.percent}%）`
}

const addrMemPie = computed(() => {
  const used = overview.value?.address_memory_usage
  const max = overview.value?.global_max_size
  if (!used || !max) return null
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
        { name: 'Address Memory', value: used, itemStyle: { color: '#0b63ce' } },
        { name: 'Free', value: Math.max(0, max - used), itemStyle: { color: FREE_COLOR } },
      ],
    }],
  }
})

const addrMemPct = computed(() => {
  const u = overview.value?.address_memory_usage
  const m = overview.value?.global_max_size
  return u && m ? Math.round((u / m) * 100) : null
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
        { name: 'Used', value: used, itemStyle: { color: '#d46b08' } },
        { name: 'Free', value: Math.max(0, max - used), itemStyle: { color: FREE_COLOR } },
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

// ---------- 消息浏览（browse() 只读预览） ----------
const messagesShow = ref(false)
const messagesLoading = ref(false)
const messages = ref<QueueMessage[]>([])
const messagesQueue = ref('')

async function viewMessages(q: QueueRow) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value || !q._mbean) return
  messagesQueue.value = q.name
  messagesShow.value = true
  messagesLoading.value = true
  try {
    messages.value = await mqApi.browse(siteId, instanceId.value, q._mbean, q.name, 20)
  } catch (e) {
    messages.value = []
    message.error((e as Error).message)
  } finally {
    messagesLoading.value = false
  }
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
        <span>{{ $t('mq.broker') }}</span>
        <n-select v-model:value="instanceId" size="small" style="width: 220px"
          :placeholder="$t('mq.instance')" :options="instances" />
        <n-button size="small" @click="load">{{ $t("common.refresh") }}</n-button>
        <tab-help topic="mq" />
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
          <div class="kv">
            <span>{{ $t('mq.versionCol') }} <b>{{ overview.version ?? '-' }}</b></span>
            <span>{{ $t('mq.uptimeCol') }} <b>{{ overview.uptime ?? '-' }}</b></span>
            <span>{{ $t('mq.connectionsCol') }} <b>{{ overview.connections ?? '-' }}</b></span>
            <span v-if="overview.sessions != null">{{ $t('mq.sessionsCol') }} <b>{{ overview.sessions }}</b></span>
            <span>{{ $t('mq.consumersCol') }} <b>{{ overview.consumers ?? '-' }}</b></span>
            <span>{{ $t('mq.addressesCol') }} <b>{{ overview.addresses ?? '-' }}</b></span>
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

      <n-card size="small" :title="`${$t('mq.queues')} (15s)`">
        <template #header-extra>
          <n-input v-model:value="queueFilter" size="small" style="width: 240px"
            :placeholder="$t('mq.search')" />
        </template>
        <div v-if="queuesError" class="pane-error">Queues 读取失败：{{ queuesError }}（每 15s 自动重试）</div>
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('mq.queueCol') }}</th><th>{{ $t('mq.addressCol') }}</th><th>{{ $t('mq.statusCol') }}</th><th>{{ $t('mq.messagesCol') }}</th><th>{{ $t('mq.consumersCol') }}</th>
              <th>{{ $t('mq.added') }}</th><th>{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in filteredQueues" :key="q.name">
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
              <td>{{ q.consumer_count ?? '-' }}</td>
              <td>{{ q.messages_added ?? '-' }}</td>
              <td>
                <n-space :size="4" :wrap="false">
                  <n-button v-if="q._mbean" size="small" style="min-width: 64px" @click="viewMessages(q)">{{ $t('mq.view') }}</n-button>
                  <!-- 清空积压：10 秒倒计时确认（破坏性操作，记录操作日志） -->
                  <countdown-confirm
                    v-if="q._mbean && (q.message_count ?? 0) > 0"
                    :label="$t('mq.purge')"
                    :confirm-text="$t('mq.purge')"
                    :target="q.name"
                    :seconds="10"
                    width="64px"
                    @confirm="emptyQueue(q)"
                  />
                  <span v-if="!q._mbean" style="color: #999">-</span>
                </n-space>
              </td>
            </tr>
            <tr v-if="!filteredQueues.length">
              <td :colspan="7"><EmptyState :title="$t('mq.noMatch')" /></td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </template>

    <n-card v-else-if="!loading" size="small">
      <span style="color: #999">该站点暂无 MQ 配置——请在「站点管理 → 资源 → ActiveMQ」中添加并测试连接</span>
    </n-card>

    <!-- 消息浏览弹窗（listMessages 只读预览，前 20 条） -->
    <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="messagesShow" preset="card"
      :title="`Messages · ${messagesQueue}`" style="width: 720px">
      <n-spin :show="messagesLoading">
        <div class="msg-note">{{ $t("mq.msgNote") }}</div>
        <div v-if="!messages.length && !messagesLoading" style="text-align: center; color: #999; padding: 24px 0">
          {{ $t("mq.queueEmpty") }}
        </div>
        <div v-for="(m, i) in messages" :key="m.message_id ?? i" class="msg-block">
          <div class="msg-head">
            <span class="mono">#{{ i + 1 }}</span>
            <span class="mono" :title="String(m.message_id ?? '')">id: {{ m.message_id ?? '-' }}</span>
            <span class="mono">{{ $t("mq.priorityCol") }} {{ m.priority ?? '-' }}</span>
            <span class="mono">{{ m.durable ? $t("mq.durable") : $t("mq.nonDurable") }}</span>
            <span v-if="m.timestamp" class="mono">{{ new Date(m.timestamp).toLocaleString() }}</span>
          </div>
          <div v-if="Object.keys(m.properties ?? {}).length" class="msg-props">
            <div v-for="(v, k) in m.properties" :key="k" class="msg-prop">
              <span class="mono prop-key">{{ k }}</span>
              <span class="mono">{{ v }}</span>
            </div>
          </div>
          <div v-else class="msg-props" style="color: #999">{{ $t("mq.noProps") }}</div>
        </div>
      </n-spin>
    </n-modal>
  </n-space>
</template>

<style scoped>
/* 卡片行布局：原生 flex（n-space 会塌缩子项宽度） */
.row {
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.grow-1 {
  flex: 1;
  min-width: 0;
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
  color: #666;
}
.kv b {
  color: #1f2329;
}
.pane-error {
  color: #d03050;
  font-size: 12px;
  margin-bottom: 8px;
}
.msg-block {
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  padding: 8px 12px;
  margin-bottom: 10px;
}
.msg-head {
  display: flex;
  gap: 16px;
  color: #666;
  font-size: 12px;
  margin-bottom: 6px;
}
.msg-props {
  background: #fafbfc;
  border: 1px solid #f0f1f3;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
}
.msg-prop {
  display: flex;
  gap: 10px;
  padding: 1px 0;
}
.prop-key {
  color: #0b63ce;
  min-width: 160px;
  word-break: break-all;
}
.msg-note {
  background: #fdf6ec;
  border: 1px solid #f3e3c3;
  color: #946b2d;
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 12px;
  margin-bottom: 10px;
}
</style>
