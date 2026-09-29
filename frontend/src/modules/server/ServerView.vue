<script setup lang="ts">
import { computed, h, inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCard,
  NDataTable,
  NModal,
  NPopconfirm,
  NProgress,
  NSelect,
  NSpace,
  NSpin,
  NTable,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import MetricCard from '../../components/MetricCard.vue'
import EmptyState from '../../components/EmptyState.vue'
import CountUp from '../../components/bits/CountUp.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples, type SamplePoint } from '../overview/api'
import { serverApi, type ProcessRow, type ServerMetrics, type ZombieRow } from './api'
import { fmtBytes, pctColor } from '../../utils/format'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()
const opsDark = inject<{ isDark: Ref<boolean> }>('opsDark')!

const servers = ref<Array<{ label: string; value: string }>>([])
const serverId = ref<string | null>(null)
const metrics = ref<ServerMetrics | null>(null)
const processes = ref<ProcessRow[]>([])
const loading = ref(false)
const error = ref('')
const cpuSeries = ref<SamplePoint[]>([])
const memSeries = ref<SamplePoint[]>([])

// 只读原则（验收 8）：本页面唯一写入口为僵尸进程终止（kill -9 走后端，记 oplog）
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

// ---- 僵尸进程：卡片计数 → 点击弹窗列表 → 逐行终止 ----
const ZOMBIE_RED = '#e5484d'
const showZombies = ref(false)
const zombies = ref<ZombieRow[]>([])
const zombieLoading = ref(false)
const zombieCount = computed(() => metrics.value?.zombie_count ?? null)

async function loadZombies() {
  if (!siteStore.currentSiteId || !serverId.value) return
  zombieLoading.value = true
  try {
    zombies.value = await serverApi.zombies(siteStore.currentSiteId, serverId.value)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    zombieLoading.value = false
  }
}

// 弹窗打开即拉取列表（kill 后也复用此函数刷新）
watch(showZombies, (v) => { if (v) loadZombies() })

async function killZombie(z: ZombieRow) {
  if (!siteStore.currentSiteId || !serverId.value) return
  try {
    await serverApi.killZombie(siteStore.currentSiteId, serverId.value, z.pid, z.comm)
    message.success(t('server.zombieKilled'))
    await loadZombies()
    load(true) // 静默刷新卡片上的计数
  } catch (e) {
    message.error((e as Error).message)
  }
}

const memPct = computed(() => {
  const m = metrics.value?.memory
  // 保留 1 位小数：整数百分比在 16GB 机器上约 157MB 才动一格，看起来"永远不变"
  return m?.total && m?.used != null ? Math.round((m.used / m.total) * 1000) / 10 : null
})

// HH:mm:ss（手动补零：不受浏览器 locale 影响，en-US 会带 AM/PM）
function hhmmss(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

const trendOption = computed(() => {
  const labels = cpuSeries.value.map((p) => hhmmss(p.ts))
  const memPoints = memSeries.value.map((p) => p.v)
  return {
    grid: { left: 44, right: 16, top: 36, bottom: 26 },
    legend: { data: [t('server.cpuCol'), t('server.memCol')], top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        // 固定步长取整秒标签（最多 ~6 个）：避免 ECharts 自动间隔导致标签"跳动"
        interval: Math.max(0, Math.ceil(labels.length / 6) - 1),
      },
    },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: t('server.cpuCol'), type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: 0.12 }, data: cpuSeries.value.map((p) => p.v) },
      { name: t('server.memCol'), type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: 0.12 }, data: memPoints },
    ],
  }
})

// 环形饼图：used vs 剩余（中心百分比由外层 HTML CountUp 叠加渲染，echarts 只画环）
function donutOption(pct: number | null | undefined, usedColor: string) {
  const v = pct ?? 0
  return {
    tooltip: { show: false },
    series: [
      {
        type: 'pie',
        radius: ['70%', '92%'],
        center: ['50%', '50%'],
        label: { show: false },
        labelLine: { show: false },
        emphasis: { disabled: true }, // hover 不淡出剩余段
        data: [
          { value: v, itemStyle: { color: usedColor } },
          { value: Math.max(0, 100 - v), itemStyle: { color: opsDark.isDark.value ? '#26262c' : '#e5e6eb' } },
        ],
      },
    ],
  }
}

const cpuDonutOption = computed(() => donutOption(metrics.value?.cpu.usage, '#2563eb'))
const memDonutOption = computed(() => donutOption(memPct.value, '#f0a020'))

// Disk 概览卡：use_percent 最高的挂载点
const topDisk = computed(() => {
  const rows = metrics.value?.disk ?? []
  if (!rows.length) return null
  return rows.reduce((a, b) => (b.use_percent > a.use_percent ? b : a))
})

// 磁盘表（NDataTable）：usage 列内联进度条，阈值变色
type DiskRow = NonNullable<ServerMetrics['disk']>[number]
const diskColumns = computed<DataTableColumns<DiskRow>>(() => [
  { title: t('server.mount'), key: 'mount' },
  { title: t('server.size'), key: 'size' },
  { title: t('server.usedCol'), key: 'used' },
  { title: t('server.availCol'), key: 'avail' },
  {
    title: t('server.usage'),
    key: 'use_percent',
    render: (row) =>
      h('div', { class: 'usage-cell' }, [
        h(NProgress, {
          percentage: row.use_percent ?? 0,
          showIndicator: false,
          height: 6,
          color: pctColor(row.use_percent),
        }),
        h(
          'span',
          { class: 'usage-num', style: { color: pctColor(row.use_percent) } },
          `${row.use_percent ?? '?'}%`,
        ),
      ]),
  },
  {
    title: t('server.inode'),
    key: 'inode_percent',
    render: (row) => `${row.inode_percent ?? '-'}%`,
  },
])

</script>

<template>
  <!-- flex 布局替代 n-space（避免重复 key 告警），间距与全局 12px 规范一致 -->
  <div class="sv-stack">
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
        <span class="poll-note">{{ $t('server.autoRefresh') }}</span>
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

      <!-- 指标卡统一 5 列网格：等宽等高，一行放下 CPU/内存/网络/磁盘/僵尸 -->
      <div class="sv-cards">
        <n-card size="small" :title="$t('server.cpu')">
          <div class="donut-wrap">
            <base-chart :option="cpuDonutOption" height="120px" />
            <div class="donut-center" :style="{ color: pctColor(metrics.cpu.usage) }">
              <CountUp v-if="metrics.cpu.usage != null" :value="metrics.cpu.usage" suffix="%" :duration="500" />
              <span v-else>?</span>
            </div>
          </div>
          <div class="metric-note">{{ $t('server.thresholdNote') }}</div>
          <div class="metric-sub">
            {{ $t('server.cores') }} {{ metrics.cpu.cores ?? '?' }} · {{ $t('server.iowait') }} {{ metrics.cpu.iowait ?? '?' }}% ·
            {{ $t('server.load') }} {{ metrics.load.load1 ?? '?' }} / {{ metrics.load.load5 ?? '?' }} / {{ metrics.load.load15 ?? '?' }}
          </div>
        </n-card>
        <n-card size="small" :title="$t('server.memory')">
          <div class="donut-wrap">
            <base-chart :option="memDonutOption" height="120px" />
            <div class="donut-center" :style="{ color: pctColor(memPct) }">
              <CountUp v-if="memPct != null" :value="memPct" :decimals="1" suffix="%" :duration="500" />
              <span v-else>?</span>
            </div>
          </div>
          <div class="metric-note">{{ $t('server.thresholdNote') }}</div>
          <!-- MB 级直出：GB 四舍五入会吃掉百 MB 级波动，看起来"数值不变" -->
          <div class="metric-sub">
            {{ $t('server.used') }} {{ metrics.memory.used }}MB / {{ $t('server.total') }} {{ metrics.memory.total }}MB
          </div>
          <div class="metric-sub">
            {{ $t('server.avail') }} {{ metrics.memory.available }}MB · {{ $t('server.swap') }} {{ metrics.memory.swap_used ?? 0 }}MB
          </div>
        </n-card>
        <n-card size="small" :title="$t('server.network')">
          <!-- 5 列布局下收窄：RX/TX 两行竖排省宽度 -->
          <div class="net-lines mono">
            <div>{{ fmtBytes(metrics.network.rx) }}<span class="unit">↓</span></div>
            <div>{{ fmtBytes(metrics.network.tx) }}<span class="unit">↑</span></div>
          </div>
          <div class="metric-sub">
            errors {{ metrics.network.errors }} · dropped {{ metrics.network.dropped }}
          </div>
        </n-card>
        <metric-card
          :title="$t('server.disk')"
          :value="topDisk?.use_percent ?? null"
          suffix="%"
          :color="pctColor(topDisk?.use_percent)"
          :bar-color="pctColor(topDisk?.use_percent)"
        >
          <template v-if="topDisk">
            {{ topDisk.mount }} · {{ $t('server.used') }} {{ topDisk.used }} / {{ $t('server.total') }} {{ topDisk.size }}
          </template>
        </metric-card>
        <!-- 僵尸进程：>0 红色告警，0 灰色健康；点击打开明细弹窗 -->
        <div class="tile-wrap" @click="showZombies = true">
          <metric-card
            :title="$t('server.zombies')"
            :value="zombieCount"
            :color="zombieCount ? ZOMBIE_RED : undefined"
            :bar-color="zombieCount ? ZOMBIE_RED : '#9ca0a8'"
          >
            {{ zombieCount ? $t('server.zombieList') : $t('server.zombieEmpty') }}
          </metric-card>
        </div>
      </div>

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

      <n-card size="small" :title="$t('server.diskTable')">
        <n-data-table
          :columns="diskColumns"
          :data="metrics.disk"
          size="small"
          :bordered="false"
          :single-line="false"
        />
      </n-card>
    </template>

    <n-card v-else-if="!error && !loading" size="small">
      <span style="color: #999">{{ $t('server.noServers') }}</span>
    </n-card>

    <!-- 僵尸进程明细弹窗：PID/PPID/STAT/CMD + 逐行终止（kill -9，后端记 oplog） -->
    <n-modal
      v-model:show="showZombies"
      preset="card"
      :mask-closable="false"
      :close-on-esc="false"
      :title="`${$t('server.zombies')} (${zombies.length})`"
      style="width: 720px"
    >
      <n-spin :show="zombieLoading">
        <empty-state v-if="!zombieLoading && !zombies.length" :title="$t('server.zombieEmpty')" />
        <n-table v-else :single-line="false" size="small">
          <thead>
            <tr>
              <th>PID</th>
              <th>PPID</th>
              <th>STAT</th>
              <th>CMD</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="z in zombies" :key="z.pid">
              <td class="mono">{{ z.pid }}</td>
              <td class="mono">{{ z.ppid }}</td>
              <td class="mono">{{ z.stat }}</td>
              <td class="cmd" :title="z.comm">{{ z.comm }}</td>
              <td>
                <n-popconfirm @positive-click="killZombie(z)">
                  <template #trigger>
                    <n-button size="tiny" type="error">{{ $t('server.killZombie') }}</n-button>
                  </template>
                  kill -9 {{ z.pid }} ?
                </n-popconfirm>
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
    </n-modal>
  </div>
</template>

<style scoped>
/* 页面纵向堆叠（替代 n-space vertical，避免重复 key 告警） */
.sv-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
/* 指标卡统一网格：5 列等宽等高（grid 默认 stretch），一行放下 CPU/内存/网络/磁盘/僵尸 */
.sv-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  align-items: stretch;
}
/* 可点击卡片（Overview tile-wrap 同款） */
.tile-wrap {
  cursor: pointer;
}
/* donut 中心数字叠加层（echarts 只画环，数字由 HTML 渲染才能接 CountUp） */
.donut-wrap {
  position: relative;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}
/* 网络卡 RX/TX 竖排两行（5 列布局下省宽度），数值 24px */
.net-lines {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.4;
}
/* 服务器选择栏的轮询频率注记 */
.poll-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
.mono {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
.metric-note {
  margin-top: 6px;
  color: var(--ops-text-3);
  font-size: 11px;
}
.unit {
  font-size: 14px;
  font-weight: 400;
  margin-left: 4px;
  color: var(--ops-text-3);
}
.metric-sub {
  margin-top: 6px;
  color: var(--ops-text-2);
  font-size: 12px;
}
.cmd {
  font-family: var(--ops-font-mono);
  font-size: 12px;
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* NDataTable usage 列：进度条 + 数字并排 */
.usage-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.usage-cell :deep(.n-progress) {
  width: 90px;
  flex: none;
}
.usage-num {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
</style>
