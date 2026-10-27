<script setup lang="ts">
import { computed, h, inject, onBeforeUnmount, onMounted, ref, watch, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { AlertTriangle, Info, Loader2 } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import OpsDataTable from '../../components/OpsDataTable.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import BaseChart from '../../components/BaseChart.vue'
import TabHelp from '../../components/TabHelp.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import MetricCard from '../../components/MetricCard.vue'
import LoadingDots from '../../components/LoadingDots.vue'
import EmptyState from '../../components/EmptyState.vue'
import TipCopy from '../../components/TipCopy.vue'
import CountUp from '../../components/bits/CountUp.vue'
import { useSiteStore } from '../../stores/site'
import { getSamples, type SamplePoint } from '../overview/api'
import { serverApi, type DiskRow, type Issue, type ProcessRow, type ServerMetrics, type ZombieGroup } from './api'
import { fmtBytes, pctColor } from '../../utils/format'

const siteStore = useSiteStore()
const messageApi = message
const { t } = useI18n()
const theme = inject<ComputedRef<'light' | 'dark'>>('opsTheme', computed(() => 'light'))

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
    messageApi.error((e as Error).message)
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

// reka Select 的值恒为字符串；空值不回写保持占位符显示
function pickServer(v: unknown) {
  if (typeof v === 'string' && v) serverId.value = v
}

// ---- 僵尸进程：卡片计数 → 点击弹窗（按父进程分组）→ 终止父进程让系统回收僵尸 ----
const ZOMBIE_RED = '#e5484d'
const showZombies = ref(false)
const zombies = ref<ZombieGroup[]>([])
const zombieTotal = ref(0)
const zombieLoading = ref(false)
const zombieCount = computed(() => metrics.value?.zombie_count ?? null)

async function loadZombies() {
  if (!siteStore.currentSiteId || !serverId.value) return
  zombieLoading.value = true
  try {
    const res = await serverApi.zombies(siteStore.currentSiteId, serverId.value)
    zombies.value = res.groups
    zombieTotal.value = res.total
  } catch (e) {
    messageApi.error((e as Error).message)
  } finally {
    zombieLoading.value = false
  }
}

// 弹窗打开即拉取列表（kill 后也复用此函数刷新）
watch(showZombies, (v) => { if (v) loadZombies() })

async function killZombie(z: ZombieGroup) {
  if (!siteStore.currentSiteId || !serverId.value) return
  try {
    await serverApi.killZombie(siteStore.currentSiteId, serverId.value, z.ppid, z.cmd)
    messageApi.success(t('server.zombieKilled'))
    await loadZombies()
    load(true) // 静默刷新卡片上的计数
  } catch (e) {
    messageApi.error((e as Error).message)
  }
}

/** 危险确认弹窗不因 Esc / 点遮罩误关（对齐原 modal mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}

const memPct = computed(() => {
  const m = metrics.value?.memory
  // 保留 1 位小数：整数百分比在 16GB 机器上约 157MB 才动一格，看起来"永远不变"
  return m?.total && m?.used != null ? Math.round((m.used / m.total) * 1000) / 10 : null
})

// 刻度统一 HH:mm:ss（手动补零，不受浏览器 locale 影响，en-US 会带 AM/PM）。
// 每 5 个样本显示一个标签（3s 采样 × 5 = 15s 一个），40 样本窗口不拥挤；hideOverlap 兜底防挤
function axisLabels(points: SamplePoint[]): string[] {
  const p = (n: number) => String(n).padStart(2, '0')
  return points.map((pt) => {
    const d = new Date(pt.ts * 1000)
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  })
}

// 趋势只展示最近 40 个样本（3s 采样 ≈ 2 分钟窗口）：采集仍拉全量，展示侧截断
const TREND_WINDOW = 40

const trendOption = computed(() => {
  const cpu = cpuSeries.value.slice(-TREND_WINDOW)
  const mem = memSeries.value.slice(-TREND_WINDOW)
  return {
    grid: { left: 44, right: 16, top: 36, bottom: 26 },
    legend: { data: [t('server.cpuCol'), t('server.memCol')], top: 0 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: axisLabels(cpu),
      axisLabel: {
        interval: 4, // 每 5 个样本一个标签（3s × 5 = 15s），全 HH:mm:ss 不拥挤
        fontSize: 10,
        hideOverlap: true,
      },
    },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: t('server.cpuCol'), type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: 0.12 }, data: cpu.map((p) => p.v) },
      { name: t('server.memCol'), type: 'line', smooth: true, showSymbol: false, areaStyle: { opacity: 0.12 }, data: mem.map((p) => p.v) },
    ],
  }
})

// 环形饼图：used vs 剩余（中心百分比由外层 HTML CountUp 叠加渲染，echarts 只画环）。
// 剩余段底色随画风三态计算（light→浅灰、mono/terminal→深灰），不再硬编码单一灰
const donutIdleColor = computed(() => (theme.value === 'light' ? '#e5e6eb' : '#26262c'))

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
          { value: Math.max(0, 100 - v), itemStyle: { color: donutIdleColor.value } },
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

// Top 进程表（只展示前 10）：排序由 OpsDataTable（TanStack）承担，不改变 top10 的入选
const topProcesses = computed(() => processes.value.slice(0, 10))

// 磁盘表：usage 列内联进度条，阈值变色；size/used/avail 按字节比较排序（保留 bySize 语义）
/** "1014M"/"31G"/"2.3T" -> 字节数（df -hP 的人类可读单位）。解析失败返回 -1 沉底。 */
function sizeToBytes(s: string | null | undefined): number {
  if (!s) return -1
  const m = /^([\d.]+)\s*([KMGTPE]?)i?B?$/i.exec(s.trim())
  if (!m) return -1
  const units: Record<string, number> = { '': 1, K: 1024, M: 1024 ** 2, G: 1024 ** 3, T: 1024 ** 4, P: 1024 ** 5, E: 1024 ** 6 }
  return parseFloat(m[1]) * (units[m[2].toUpperCase()] ?? 1)
}

const diskColumns = computed<any[]>(() => [
  {
    accessorKey: 'mount',
    header: t('server.mount'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as DiskRow).mount,
  },
  {
    accessorFn: (r: DiskRow) => sizeToBytes(r.size),
    id: 'size',
    header: t('server.size'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as DiskRow).size,
  },
  {
    accessorFn: (r: DiskRow) => sizeToBytes(r.used),
    id: 'used',
    header: t('server.usedCol'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as DiskRow).used,
  },
  {
    accessorFn: (r: DiskRow) => sizeToBytes(r.avail),
    id: 'avail',
    header: t('server.availCol'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as DiskRow).avail,
  },
  {
    accessorKey: 'use_percent',
    header: t('server.usage'),
    sortDescFirst: false,
    cell: (ctx: any) => {
      const v = (ctx.row.original as DiskRow).use_percent
      return h('div', { class: 'flex items-center gap-2' }, [
        h(Progress, { value: v ?? 0, dangerAt: 90, class: 'w-[90px] flex-none' }),
        h('span', { class: 'font-mono font-semibold tabular-nums', style: { color: pctColor(v) } }, `${v ?? '?'}%`),
      ])
    },
  },
  {
    accessorKey: 'inode_percent',
    header: t('server.inode'),
    sortDescFirst: false,
    cell: (ctx: any) => `${(ctx.row.original as DiskRow).inode_percent ?? '-'}%`,
  },
])

const issueColumns = computed<any[]>(() => [
  {
    accessorKey: 'severity',
    header: t('server.level'),
    enableSorting: false,
    cell: (ctx: any) => h(StatusBadge, { status: (ctx.row.original as Issue).severity }),
  },
  { accessorKey: 'type', header: t('server.type'), enableSorting: false, cell: (ctx: any) => (ctx.row.original as Issue).type },
  { accessorKey: 'value', header: t('server.value'), enableSorting: false, cell: (ctx: any) => (ctx.row.original as Issue).value },
  { accessorKey: 'threshold', header: t('server.threshold'), enableSorting: false, cell: (ctx: any) => (ctx.row.original as Issue).threshold },
  {
    id: 'detail',
    header: t('server.detail'),
    enableSorting: false,
    cell: (ctx: any) => {
      const i = ctx.row.original as Issue
      return t(`server.issue_${i.type}`, { value: i.value, threshold: i.threshold, mount: i.mount ?? '-' })
    },
  },
])

const processColumns = computed<any[]>(() => [
  {
    accessorKey: 'pid',
    header: t('server.pid'),
    sortDescFirst: false,
    cell: (ctx: any) => h('span', { class: 'font-mono tabular-nums' }, (ctx.row.original as ProcessRow).pid),
  },
  {
    accessorKey: 'cpu_percent',
    header: t('server.cpuCol'),
    sortDescFirst: false,
    cell: (ctx: any) => {
      const p = ctx.row.original as ProcessRow
      return h('span', { style: { color: pctColor(p.cpu_percent) } }, p.cpu_percent)
    },
  },
  {
    accessorKey: 'mem_percent',
    header: t('server.memCol'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as ProcessRow).mem_percent,
  },
  {
    accessorKey: 'command',
    header: t('server.command'),
    cell: (ctx: any) => {
      const p = ctx.row.original as ProcessRow
      return h('span', { class: 'block max-w-[420px] truncate font-mono', title: p.command }, p.command)
    },
  },
])

const zombieColumns = computed<any[]>(() => [
  {
    accessorKey: 'ppid',
    header: t('server.zParentPid'),
    sortDescFirst: false,
    cell: (ctx: any) => h('span', { class: 'font-mono tabular-nums' }, (ctx.row.original as ZombieGroup).ppid),
  },
  {
    accessorKey: 'count',
    header: t('server.zCount'),
    sortDescFirst: false,
    cell: (ctx: any) => h('span', { class: 'font-mono tabular-nums' }, (ctx.row.original as ZombieGroup).count),
  },
  {
    accessorKey: 'cmd',
    header: t('server.zCmd'),
    cell: (ctx: any) => h(TipCopy, { text: (ctx.row.original as ZombieGroup).cmd, max: 380 }),
  },
  {
    id: 'actions',
    header: '',
    enableSorting: false,
    cell: (ctx: any) => {
      const z = ctx.row.original as ZombieGroup
      // kill -9 属不可逆写操作：倒计时确认（组件内置 AlertDialog），确认后走后端并记 oplog
      return h(CountdownConfirm, {
        label: t('server.killZombie'),
        confirmText: t('server.killZombie'),
        target: t('server.killZombieConfirm', { pid: z.ppid }),
        seconds: 3,
        width: '64px',
        onConfirm: () => killZombie(z),
      })
    },
  },
])

</script>

<template>
  <!-- flex 布局替代 n-space，间距与全局 12px 规范一致 -->
  <div class="sv-stack">
    <Card>
      <CardContent class="flex flex-wrap items-center gap-3">
        <span>{{ $t('server.title') }}</span>
        <Select :model-value="serverId" @update:model-value="pickServer">
          <SelectTrigger class="w-[240px]" :placeholder="$t('server.select')" />
          <SelectContent>
            <SelectItem v-for="s in servers" :key="s.value" :value="s.value">{{ s.label }}</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" :disabled="loading" @click="load(false)">
          <Loader2 v-if="loading" class="animate-spin" />
          {{ $t('server.refresh') }}
        </Button>
        <tab-help topic="server" />
        <span class="poll-note">{{ $t('server.autoRefresh') }}</span>
        <!-- 已存资源的行级测试需 per-resource test 端点（PRD §18 POST .../test），落地后补 -->
        <status-badge v-if="metrics" :status="metrics.diagnosis?.status" />
      </CardContent>
    </Card>

    <Card v-if="error">
      <CardHeader><CardTitle>{{ $t('server.queryFailed') }}</CardTitle></CardHeader>
      <CardContent class="text-sm text-muted-foreground">
        {{ error }}{{ $t('server.failedNote') }}
      </CardContent>
    </Card>

    <!-- 首载 loading（全站统一 LoadingDots 风格） -->
    <Card v-if="loading && !metrics && !error">
      <CardContent class="flex justify-center py-14">
        <loading-dots :text="$t('common.loading')" />
      </CardContent>
    </Card>

    <template v-if="metrics">
      <Card v-if="metrics.diagnosis?.issues?.length">
        <CardHeader><CardTitle>{{ $t('server.issues') }}</CardTitle></CardHeader>
        <CardContent>
          <OpsDataTable :columns="issueColumns" :data="metrics.diagnosis.issues" />
        </CardContent>
      </Card>

      <!-- 指标卡统一 MetricCard：5 列网格等宽等高；仅僵尸卡可点击（弹窗明细），也只有它开 hover 边框 -->
      <div class="sv-cards">
        <metric-card :title="$t('server.cpu')">
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
        </metric-card>
        <metric-card :title="$t('server.memory')">
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
        </metric-card>
        <metric-card :title="$t('server.network')">
          <!-- 5 列布局下收窄：RX/TX 两行竖排省宽度 -->
          <div class="net-lines mono">
            <div>{{ fmtBytes(metrics.network.rx) }}<span class="unit">↓</span></div>
            <div>{{ fmtBytes(metrics.network.tx) }}<span class="unit">↑</span></div>
          </div>
          <div class="metric-sub">
            {{ $t('server.netErrors') }} {{ metrics.network.errors }} · {{ $t('server.netDropped') }} {{ metrics.network.dropped }}
          </div>
        </metric-card>
        <metric-card
          :title="$t('server.disk')"
          :value="topDisk?.use_percent ?? null"
          suffix="%"
          :color="pctColor(topDisk?.use_percent)"
        >
          <template v-if="topDisk">
            {{ topDisk.mount }} · {{ $t('server.used') }} {{ topDisk.used }} / {{ $t('server.total') }} {{ topDisk.size }}
          </template>
        </metric-card>
        <!-- 僵尸进程：>0 红色告警，0 灰色健康；点击卡片本体（非外层包装）打开明细弹窗 -->
        <metric-card
          class="tile-click"
          hoverable
          :title="$t('server.zombies')"
          :value="zombieCount"
          :color="zombieCount ? ZOMBIE_RED : undefined"
          :bar-color="zombieCount ? ZOMBIE_RED : '#9ca0a8'"
          @click="showZombies = true"
        >
          {{ zombieCount ? $t('server.zombieList') : $t('server.zombieEmpty') }}
        </metric-card>
      </div>

      <Card>
        <CardHeader><CardTitle>{{ $t('server.trend') }}</CardTitle></CardHeader>
        <CardContent>
          <base-chart v-if="cpuSeries.length" :option="trendOption" height="220px" />
          <div v-else class="py-3 text-center text-xs text-muted-foreground">
            {{ $t('server.emptyMetrics') }}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{{ $t('server.topProcesses') }}</CardTitle></CardHeader>
        <CardContent>
          <OpsDataTable :columns="processColumns" :data="topProcesses" size="compact" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{{ $t('server.diskTable') }}</CardTitle></CardHeader>
        <CardContent>
          <OpsDataTable :columns="diskColumns" :data="metrics.disk" size="compact" />
        </CardContent>
      </Card>
    </template>

    <Card v-else-if="!error && !loading">
      <CardContent>
        <span class="text-sm text-muted-foreground">{{ $t('server.noServers') }}</span>
      </CardContent>
    </Card>

    <!-- 僵尸进程明细弹窗：按父进程分组（父进程 PID/僵尸数/父进程命令），kill 的是父进程 -->
    <Dialog :open="showZombies" @update:open="showZombies = $event">
      <DialogContent
        class="w-[860px] max-w-[94vw]"
        @escape-key-down="blockDismiss"
        @interact-outside="blockDismiss"
      >
        <DialogHeader><DialogTitle>{{ $t('server.zombies') }} ({{ zombieTotal }})</DialogTitle></DialogHeader>
        <!-- 什么是僵尸：没有这句用户会把「父进程命令」误读为僵尸本体 -->
        <div class="zombie-hint">
          <Info class="size-4 flex-none" />
          <span>{{ $t('server.zombieHint') }}</span>
        </div>
        <div v-if="zombieLoading" class="flex justify-center py-10">
          <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
        </div>
        <template v-else>
          <EmptyState v-if="!zombies.length" :title="$t('server.zombieEmpty')" />
          <!-- 僵尸风暴（数千僵尸 = 数千分组行）必须分页，否则整表渲染打爆页面 -->
          <template v-else>
            <OpsDataTable :columns="zombieColumns" :data="zombies" row-key="ppid" :page-size="50" />
            <!-- kill 是杀父进程：父进程往往是业务/容器主进程，必须显式警告 -->
            <div class="zombie-kill-warn">
              <AlertTriangle class="size-4 flex-none" />
              <span>{{ $t('server.killWarn') }}</span>
            </div>
          </template>
        </template>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
<style scoped>
.zombie-hint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ops-text-2);
  background: color-mix(in srgb, var(--primary) 7%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary) 25%, transparent);
  border-radius: 6px;
}
.zombie-hint svg {
  color: var(--primary);
  margin-top: 2px;
}
.zombie-kill-warn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ops-critical);
  background: color-mix(in srgb, var(--ops-critical) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--ops-critical) 30%, transparent);
  border-radius: 6px;
}
/* 页面纵向堆叠，间距与全局 12px 规范一致 */
.sv-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
/* 指标卡统一网格：等宽等高（grid 默认 stretch），卡片即网格项；窄屏自动减列换行 */
.sv-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  align-items: stretch;
}
/* 唯一可点击卡片（僵尸进程）：点击绑定在卡片本体上，点击区域与卡片完全一致 */
.tile-click {
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
/* 网络卡 RX/TX 竖排两行（5 列布局下省宽度），数值 24px；
   覆写 mc-extra 的 text-3：数值用 text-1 提高对比度 */
.net-lines {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--ops-text-1);
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
  color: var(--ops-text-2);
}
.metric-sub {
  margin-top: 6px;
  color: var(--ops-text-2);
  font-size: 12px;
}
</style>
