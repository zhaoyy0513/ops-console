<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CircleCheck, CircleX, RefreshCw } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TipCopy from '../../components/TipCopy.vue'
import { useSiteStore } from '../../stores/site'
import { netdiagApi, type NetdiagRow } from './api'

const { t, locale } = useI18n()
const siteStore = useSiteStore()

const rows = ref<NetdiagRow[]>([])
const loading = ref(false)
const probedAt = ref<Date | null>(null)

const okCount = computed(() => rows.value.filter((r) => r.ok).length)
const failCount = computed(() => rows.value.length - okCount.value)

const TYPE_LABEL: Record<string, string> = {
  servers: 'netdiag.typeServers',
  redis: 'netdiag.typeRedis',
  mq: 'netdiag.typeMq',
  devices: 'netdiag.typeDevices',
}

const lastProbe = computed(() =>
  probedAt.value
    ? probedAt.value.toLocaleTimeString(locale.value === 'zh' ? 'zh-CN' : 'en-US', { hour12: false })
    : t('netdiag.never'),
)

async function probe() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    rows.value = await netdiagApi.matrix(siteId)
    probedAt.value = new Date()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(probe)
watch(() => siteStore.currentSiteId, () => {
  rows.value = []
  probedAt.value = null
  probe()
})

/** 失败行标红；可达但耗时 >1s 标黄 */
function rowClass(r: NetdiagRow): string {
  if (!r.ok) return 'row-fail'
  return r.latency_ms > 1000 ? 'row-slow' : ''
}
</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('netdiag.title') }}</CardTitle>
      <span class="flex items-center gap-3">
        <span class="text-xs text-muted-foreground">
          {{ $t('netdiag.lastProbe') }}：{{ lastProbe }}
        </span>
        <Button size="sm" :disabled="!siteStore.currentSiteId || loading" @click="probe">
          <RefreshCw :class="loading ? 'animate-spin' : ''" />
          {{ $t('netdiag.reprobe') }}
        </Button>
      </span>
    </CardHeader>
    <CardContent>
      <div v-if="rows.length" class="summary">
        {{ $t('netdiag.summary', { total: rows.length, ok: okCount, fail: failCount }) }}
      </div>

      <div v-if="loading && !rows.length" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>

      <div v-else-if="rows.length" class="w-full overflow-x-auto">
        <table class="matrix">
          <thead>
            <tr>
              <th>{{ $t('netdiag.colType') }}</th>
              <th>{{ $t('netdiag.colName') }}</th>
              <th>{{ $t('netdiag.colAddress') }}</th>
              <th>{{ $t('netdiag.colResult') }}</th>
              <th class="num">{{ $t('netdiag.colLatency') }}</th>
              <th>{{ $t('netdiag.colError') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="`${r.resource_type}-${r.resource_name}-${r.host}-${r.port}`" :class="rowClass(r)">
              <td>{{ $t(TYPE_LABEL[r.resource_type] ?? r.resource_type) }}</td>
              <td class="name">{{ r.resource_name }}</td>
              <td class="mono">{{ r.host }}:{{ r.port ?? '-' }}</td>
              <td>
                <span class="result" :class="r.ok ? 'ok' : 'fail'">
                  <component :is="r.ok ? CircleCheck : CircleX" class="size-3.5" />
                  {{ r.ok ? $t('netdiag.reachable') : $t('netdiag.unreachable') }}
                </span>
              </td>
              <td class="num mono">{{ r.latency_ms }} ms</td>
              <td><tip-copy :text="r.error ?? '-'" :max="320" /></td>
            </tr>
          </tbody>
        </table>
      </div>

      <empty-state v-else :title="$t('netdiag.empty')" />
    </CardContent>
  </Card>
</template>

<style scoped>
.summary {
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--ops-text-2);
  font-variant-numeric: tabular-nums;
}
.matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.matrix th {
  height: 36px;
  padding: 0 12px;
  text-align: left;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
  background: var(--muted);
  border-bottom: 1px solid var(--border);
}
.matrix td {
  padding: 8px 12px;
  white-space: nowrap;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  color: var(--foreground);
}
.matrix tbody tr:last-child td {
  border-bottom: 0;
}
.matrix tbody tr {
  transition: background 120ms ease;
}
.matrix tbody tr:hover {
  background: var(--muted);
}
.row-fail {
  background: color-mix(in srgb, var(--destructive) 10%, transparent);
}
.row-fail:hover {
  background: color-mix(in srgb, var(--destructive) 16%, transparent);
}
.row-slow {
  background: color-mix(in srgb, var(--ops-warning) 10%, transparent);
}
.row-slow:hover {
  background: color-mix(in srgb, var(--ops-warning) 16%, transparent);
}
.name {
  font-weight: 500;
}
.mono {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
.num {
  text-align: right;
}
.result {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}
.result.ok {
  color: var(--ops-healthy);
}
.result.fail {
  color: var(--destructive);
}
</style>
