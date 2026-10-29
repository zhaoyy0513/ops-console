<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { message } from '@/lib/message'
import OpsDataTable from '../../components/OpsDataTable.vue'
import { useSiteStore } from '../../stores/site'
import { locale } from '../../i18n'
import { DEVICE_FIELDS } from './fields'
import TabHelp from '../../components/TabHelp.vue'
import CodeJsonEditor from '../../components/CodeJsonEditor.vue'
import TipCopy from '../../components/TipCopy.vue'
import { deviceApi, type DeviceCustomField, type DeviceHealth, type DeviceRow } from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const REFRESH_SECONDS = 30

/** 状态徽标语义映射（device 侧状态词 -> Badge variant） */
function statusVariant(r: DeviceRow): 'success' | 'warning' | 'critical' | 'secondary' {
  const s = String(r.status ?? '').toLowerCase()
  if (['error', 'fault', 'offline', 'down'].includes(s) || r.error) return 'critical'
  if (['running', 'working', 'active', 'online'].includes(s)) return 'success'
  if (['idle', 'charging', 'standby', 'paused'].includes(s)) return 'warning'
  return 'secondary'
}

const instances = ref<Array<{ label: string; value: string; custom_fields: DeviceCustomField[] }>>([])
const instanceId = ref<string | null>(null)
const devices = ref<DeviceRow[]>([])
const health = ref<DeviceHealth | null>(null)
const missingFields = computed(() => health.value?.missing_fields ?? [])
const loading = ref(false)
const detail = ref<DeviceRow | null>(null)
const detailShow = ref(false)

// 当前实例的自定义字段（列配置来自实例配置，随下拉切换）
const currentCustomFields = computed(() => instances.value.find((i) => i.value === instanceId.value)?.custom_fields ?? [])

/** 自定义字段标题：随语言取中/英文名，一种为空回退另一种 */
function cfLabel(cf: DeviceCustomField): string {
  const v = locale.value === 'zh' ? cf.label_zh : cf.label_en
  return v || cf.label_zh || cf.label_en
}

function cfVal(r: DeviceRow, key: string): string {
  return r[key] == null ? '' : String(r[key])
}

async function loadInstances() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'devices')
    instances.value = list.map((r) => ({
      label: r.name,
      value: r.id,
      custom_fields: ((r.custom_fields as DeviceCustomField[] | null) ?? []),
    }))
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

let listWasOk = true
async function load(silent = false) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value) return
  loading.value = true
  health.value = null
  try {
    // 先取健康（耗时/映射失效），列表随后命中同一份缓存；上游失败时健康也带回耗时
    health.value = await deviceApi.health(siteId, instanceId.value).catch(() => null)
    devices.value = await deviceApi.list(siteId, instanceId.value)
    listWasOk = true
  } catch (e) {
    devices.value = []
    // 轮询仅在 成功->失败 边缘提示一次（避免轮询 toast 轰炸）；手动刷新始终立即提示
    if (!silent || listWasOk) message.error((e as Error).message)
    listWasOk = false
  } finally {
    loading.value = false
  }
}

function openDetail(r: DeviceRow) {
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

// 30s 轮询（标签切走暂停，回来恢复；间隔标注在 Devices 标题旁）
let pollTimer: number | null = null
function startPolling() {
  if (pollTimer != null) return
  pollTimer = window.setInterval(() => {
    if (instanceId.value && !document.hidden && !loading.value) load(true)
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
  devices.value = []
  loadInstances()
})
watch(instanceId, () => load())

// ---------- 表格列（TanStack duck-type；排序由 OpsDataTable 承担，随自定义字段动态增列） ----------
const deviceColumns = computed<any[]>(() => {
  const cols: any[] = DEVICE_FIELDS.map((f) => ({
    accessorKey: f.key,
    header: t(`device.fields.${f.key}`),
    cell: (ctx: any) => {
      const r: DeviceRow = ctx.row.original
      if (f.key === 'status') {
        return h(Badge, { variant: statusVariant(r), size: 'sm' }, () => r.status ?? '-')
      }
      if (f.key === 'battery') {
        if (r.battery == null) return '-'
        const low = Number(r.battery) < 20
        return h('div', { class: ['bat-cell', { low }] }, [
          h(Progress, { value: Number(r.battery), class: 'w-11 flex-none' }),
          h('span', { class: 'mono-num', style: low ? { color: 'var(--destructive)' } : undefined }, `${r.battery}%`),
        ])
      }
      return r[f.key] ?? '-'
    },
  }))
  // 自定义字段列：长内容省略号，悬停 tooltip 展示全文 + 复制
  for (const cf of currentCustomFields.value) {
    cols.push({
      accessorKey: cf.key,
      header: cfLabel(cf),
      cell: (ctx: any) => h(TipCopy, { text: cfVal(ctx.row.original as DeviceRow, cf.key) }),
    })
  }
  // 操作列
  cols.push({
    accessorKey: 'actions',
    header: t('common.actions'),
    enableSorting: false,
    cell: (ctx: any) =>
      h(Button, { variant: 'outline', size: 'sm', onClick: () => openDetail(ctx.row.original as DeviceRow) },
        () => t('device.detail')),
  })
  return cols
})

// ---------- 详情弹窗表（基础信息 + 自定义字段） ----------
const detailColumns = computed<any[]>(() => {
  const base = [
    { accessorKey: 'id', header: t('device.deviceCode'), cell: (ctx: any) => h('span', { class: 'font-mono' }, ctx.row.original.id ?? '-') },
    { accessorKey: 'name', header: t('device.deviceName'), cell: (ctx: any) => ctx.row.original.name ?? '-' },
    { accessorKey: 'battery', header: t('device.battery'), cell: (ctx: any) => `${ctx.row.original.battery ?? '-'}${ctx.row.original.battery != null ? '%' : ''}` },
    { accessorKey: 'station', header: t('device.position'), cell: (ctx: any) => ctx.row.original.station ?? '-' },
    { accessorKey: 'last_update', header: t('device.lastUpdate'), cell: (ctx: any) => fmtTime(ctx.row.original.last_update) },
  ]
  for (const cf of currentCustomFields.value) {
    base.push({
      accessorKey: cf.key,
      header: cfLabel(cf),
      cell: (ctx: any) => h(TipCopy, { text: cfVal(ctx.row.original as DeviceRow, cf.key) }),
    })
  }
  return base
})

// Esc / 遮罩点击不得关窗（对齐原 n-modal mask-closable=false / close-on-esc=false）
function blockDismiss(e: Event) {
  e.preventDefault()
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card>
      <CardContent class="flex flex-wrap items-center gap-3">
        <span>{{ $t('device.instance') }}</span>
        <div class="w-60">
          <Select :model-value="instanceId ?? ''" @update:model-value="instanceId = String($event)">
            <SelectTrigger :placeholder="$t('device.selectInstance')" />
            <SelectContent>
              <SelectItem v-for="opt in instances" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" :disabled="loading" @click="load()">
          <span v-if="loading" class="inline-block size-3.5 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
          {{ $t('common.refresh') }}
        </Button>
        <tab-help topic="device" />
        <span class="text-xs text-muted-foreground">{{ $t('device.mappingHint') }}</span>
        <span
          v-if="health && health.latency_ms != null"
          class="mono-num text-xs"
          :class="health.latency_ms > 2000 ? 'text-[var(--ops-warning)]' : 'text-muted-foreground'"
        >
          {{ $t('device.latency', { ms: health.latency_ms }) }}
        </span>
        <!-- 字段映射失效：点开列出「业务字段 ← 上游路径」；无失效不渲染 -->
        <details v-if="missingFields.length" class="basis-full text-xs text-[var(--ops-warning)]">
          <summary class="cursor-pointer select-none">
            {{ $t('device.mappingBroken', { n: missingFields.length }) }}
          </summary>
          <ul class="mt-1 space-y-0.5 pl-4">
            <li v-for="m in missingFields" :key="m.field">
              <span class="font-mono">{{ m.field }}</span> ← <span class="font-mono">{{ m.source }}</span>
            </li>
          </ul>
        </details>
      </CardContent>
    </Card>

    <Card>
      <CardHeader><CardTitle>{{ $t('device.devicesTitle', { n: REFRESH_SECONDS }) }}</CardTitle></CardHeader>
      <CardContent>
        <OpsDataTable :columns="deviceColumns" :data="devices" row-key="id" mono>
          <template #empty>{{ instanceId ? $t('device.emptyInstance') : $t('device.emptyNone') }}</template>
        </OpsDataTable>
      </CardContent>
    </Card>

    <!-- 详情弹窗：基础信息 + 完整 JSON -->
    <Dialog :open="detailShow" @update:open="detailShow = $event">
      <DialogContent class="w-[640px] max-w-[94vw]" @escape-key-down="blockDismiss" @interact-outside="blockDismiss">
        <DialogHeader><DialogTitle>{{ $t('device.detailTitle', { id: detail?.id ?? '' }) }}</DialogTitle></DialogHeader>
        <template v-if="detail">
          <OpsDataTable :columns="detailColumns" :data="[detail]" row-key="id" mono size="compact" />
          <div class="text-[13px] text-muted-foreground">{{ $t('device.rawJson') }}</div>
          <CodeJsonEditor :model-value="detailJson" readonly height="320px" />
        </template>
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.bat-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
/* 电量 <20%：条与数字同步变红（Progress 指示条固定 bg-primary，就地覆写） */
.bat-cell.low :deep(.bg-primary) {
  background: var(--destructive);
}
.mono-num {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}
</style>
