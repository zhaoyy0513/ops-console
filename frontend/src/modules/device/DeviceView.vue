<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCard, NModal, NProgress, NSelect, NSpace, NTable, NTag, NTooltip, useMessage } from 'naive-ui'
import { useSiteStore } from '../../stores/site'
import { locale } from '../../i18n'
import { DEVICE_FIELDS } from './fields'
import TabHelp from '../../components/TabHelp.vue'
import CodeJsonEditor from '../../components/CodeJsonEditor.vue'
import { deviceApi, type DeviceCustomField, type DeviceRow } from './api'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()

const REFRESH_SECONDS = 30

/** 状态徽标语义映射（device 侧状态词 -> 红绿灯） */
function statusTagType(r: DeviceRow): 'success' | 'warning' | 'error' | 'default' {
  const s = String(r.status ?? '').toLowerCase()
  if (['error', 'fault', 'offline', 'down'].includes(s) || r.error) return 'error'
  if (['running', 'working', 'active', 'online'].includes(s)) return 'success'
  if (['idle', 'charging', 'standby', 'paused'].includes(s)) return 'warning'
  return 'default'
}

const instances = ref<Array<{ label: string; value: string; custom_fields: DeviceCustomField[] }>>([])
const instanceId = ref<string | null>(null)
const devices = ref<DeviceRow[]>([])
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

/** 复制自定义字段全文（表格省略号 / 详情弹窗共用） */
async function copyText(s: string) {
  try {
    await navigator.clipboard.writeText(s)
    message.success(t('common.copied'))
  } catch (e) {
    message.error(String(e))
  }
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
  try {
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
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>{{ $t('device.instance') }}</span>
        <n-select v-model:value="instanceId" size="small" style="width: 240px"
          :placeholder="$t('device.selectInstance')" :options="instances" />
        <n-button size="small" :loading="loading" @click="load()">{{ $t('common.refresh') }}</n-button>
        <tab-help topic="device" />
        <span style="color: #999; font-size: 12px">{{ $t('device.mappingHint') }}</span>
      </n-space>
    </n-card>

    <n-card size="small" :title="$t('device.devicesTitle', { n: REFRESH_SECONDS })">
      <n-table :single-line="false" size="small">
        <thead>
          <tr>
            <!-- 表头由 device/fields.ts 公用定义驱动（与字段映射配置同源），文案随语言切换；
                 自定义字段列取实例配置的双语展示名（随语言回退） -->
            <th v-for="f in DEVICE_FIELDS" :key="f.key">{{ $t(`device.fields.${f.key}`) }}</th>
            <th v-for="cf in currentCustomFields" :key="cf.key" style="min-width: 120px">{{ cfLabel(cf) }}</th>
            <th style="width: 80px">{{ $t('device.action') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in devices" :key="r.id ?? ''">
            <td v-for="f in DEVICE_FIELDS" :key="f.key" :class="{ mono: f.key === 'id' }">
              <template v-if="f.key === 'status'">
                <n-tag :type="statusTagType(r)" size="small" :bordered="false">{{ r.status ?? '-' }}</n-tag>
              </template>
              <template v-else-if="f.key === 'battery'">
                <div v-if="r.battery != null" class="bat-cell">
                  <n-progress
                    type="line"
                    :percentage="Number(r.battery)"
                    :height="5"
                    :show-indicator="false"
                    :color="Number(r.battery) < 20 ? '#d03050' : undefined"
                    :rail-color="'var(--ops-surface-2)'"
                    style="width: 44px; flex: none"
                  />
                  <span class="mono" :style="{ color: Number(r.battery) < 20 ? '#d03050' : undefined }">{{ r.battery }}%</span>
                </div>
                <span v-else>-</span>
              </template>
              <template v-else>{{ r[f.key] ?? '-' }}</template>
            </td>
            <!-- 自定义字段列：长内容省略号，悬停 tooltip 展示全文 + 复制 -->
            <td v-for="cf in currentCustomFields" :key="cf.key">
              <n-tooltip :disabled="!cfVal(r, cf.key)" style="max-width: 380px">
                <template #trigger>
                  <div class="cf-cell">{{ cfVal(r, cf.key) || '-' }}</div>
                </template>
                <div class="cf-tip">
                  <span class="cf-tip-text">{{ cfVal(r, cf.key) }}</span>
                  <n-button size="tiny" @click="copyText(cfVal(r, cf.key))">{{ $t('common.copy') }}</n-button>
                </div>
              </n-tooltip>
            </td>
            <td><n-button size="tiny" @click="openDetail(r)">{{ $t('device.detail') }}</n-button></td>
          </tr>
          <tr v-if="!devices.length && !loading">
            <td :colspan="DEVICE_FIELDS.length + currentCustomFields.length + 1" style="text-align: center; color: #999">
              {{ instanceId ? $t('device.emptyInstance') : $t('device.emptyNone') }}
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- 详情弹窗：基础信息 + 完整 JSON -->
    <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="detailShow" preset="card"
      :title="$t('device.detailTitle', { id: detail?.id ?? '' })" style="width: 640px">
      <template v-if="detail">
        <n-table :single-line="false" size="small">
          <tbody>
            <tr><th style="width: 140px">{{ $t('device.deviceCode') }}</th><td style="font-family: ui-monospace, monospace">{{ detail.id ?? '-' }}</td></tr>
            <tr><th>{{ $t('device.deviceName') }}</th><td>{{ detail.name ?? '-' }}</td></tr>
            <tr><th>{{ $t('device.battery') }}</th><td>{{ detail.battery ?? '-' }}{{ detail.battery != null ? '%' : '' }}</td></tr>
            <tr><th>{{ $t('device.position') }}</th><td>{{ detail.station ?? '-' }}</td></tr>
            <tr><th>{{ $t('device.lastUpdate') }}</th><td>{{ fmtTime(detail.last_update) }}</td></tr>
            <!-- 自定义字段：标题随语言，长内容省略号 + tooltip 全文 + 复制 -->
            <tr v-for="cf in currentCustomFields" :key="cf.key">
              <th>{{ cfLabel(cf) }}</th>
              <td>
                <n-tooltip :disabled="!cfVal(detail, cf.key)" style="max-width: 380px">
                  <template #trigger>
                    <div class="cf-cell">{{ cfVal(detail, cf.key) || '-' }}</div>
                  </template>
                  <div class="cf-tip">
                    <span class="cf-tip-text">{{ cfVal(detail, cf.key) }}</span>
                    <n-button size="tiny" @click="copyText(cfVal(detail, cf.key))">{{ $t('common.copy') }}</n-button>
                  </div>
                </n-tooltip>
              </td>
            </tr>
          </tbody>
        </n-table>
        <div style="margin: 14px 0 6px; color: var(--ops-text-2); font-size: 13px">{{ $t('device.rawJson') }}</div>
        <CodeJsonEditor :model-value="detailJson" readonly height="320px" />
      </template>
    </n-modal>
  </n-space>
</template>

<style scoped>
.bat-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.bat-cell .mono {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}
/* 自定义字段单元格：n-table 默认自动布局（仅 SshView 自带 fixed），
   内层 div 需定宽上限才能触发省略号；列本身 min-width 120px 自然拉伸 */
.cf-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cf-tip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.cf-tip-text {
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
}
</style>
