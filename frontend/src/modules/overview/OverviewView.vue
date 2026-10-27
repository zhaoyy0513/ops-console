<script setup lang="ts">
import { onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { Server, Layers, Activity, HardDriveDownload } from 'lucide-vue-next'
import LoadingDots from '../../components/LoadingDots.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { message } from '@/lib/message'
import StatusBadge from '../../components/StatusBadge.vue'
import TabHelp from '../../components/TabHelp.vue'
import MetricCard from '../../components/MetricCard.vue'
import { useSiteStore } from '../../stores/site'
import { overviewApi, type OverviewData } from './api'

const siteStore = useSiteStore()
const router = useRouter()

const data = ref<OverviewData | null>(null)
const loading = ref(false)

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    data.value = await overviewApi.get(siteId)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function refresh() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    await overviewApi.refresh(siteId)
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => siteStore.currentSiteId, load)

const KIND_META: Record<string, { label: string; route: string; icon: Component }> = {
  server: { label: 'Server', route: 'server', icon: Server },
  redis: { label: 'Redis', route: 'redis', icon: Layers },
  mq: { label: 'ActiveMQ', route: 'mq', icon: Activity },
  device: { label: 'Device', route: 'device', icon: HardDriveDownload },
}

/** tile 顶边色：有 critical 红、有 warning 黄、全健康绿、无资源灰 */
function tileBar(s: { total: number; healthy: number; warning: number; critical: number }): string {
  if (s.critical > 0) return 'var(--ops-critical)'
  if (s.warning > 0) return 'var(--ops-warning)'
  if (s.total > 0) return 'var(--ops-healthy)'
  return 'var(--ops-unknown)'
}

function goIssueModule(kind: string) {
  const meta = KIND_META[kind]
  if (meta) router.push(`/console/site/${siteStore.currentSiteId}/${meta.route}`)
}

function fmtTime(iso: string): string {
  return iso ? iso.replace('T', ' ').slice(5, 19) : '-'
}
</script>

<template>
  <div class="ov-stack">
    <Card>
      <CardContent class="ov-bar">
        <span class="text-base font-semibold">{{ data?.site.name ?? siteStore.currentSiteId }}</span>
        <status-badge v-if="data" :status="data.overall" />
        <Button variant="outline" size="sm" :disabled="loading" @click="refresh">{{ $t('overview.checkNow') }}</Button>
        <tab-help topic="overview" />
        <span v-if="data?.checked_at" class="text-xs text-muted-foreground">
          {{ $t('overview.lastCheck', { time: fmtTime(data.checked_at) }) }}
        </span>
      </CardContent>
    </Card>

    <!-- 首载 loading（全站统一 LoadingDots 风格） -->
    <Card v-if="loading && !data">
      <CardContent class="flex justify-center py-14">
        <loading-dots :text="$t('common.loading')" />
      </CardContent>
    </Card>

    <div v-if="data" class="ov-tiles">
      <div v-for="(_, kind) in KIND_META" :key="kind" class="tile-wrap" @click="goIssueModule(kind)">
        <metric-card
          :title="$t(`tabs.${kind}`)"
          :icon="KIND_META[kind].icon"
          :value="data.summary[kind as keyof typeof data.summary].total"
          :bar-color="tileBar(data.summary[kind as keyof typeof data.summary])"
          hoverable
        >
          <span class="dist">
            <Badge variant="success" size="sm">{{ data.summary[kind as keyof typeof data.summary].healthy }}</Badge>
            <Badge v-if="data.summary[kind as keyof typeof data.summary].warning" variant="warning" size="sm">{{ data.summary[kind as keyof typeof data.summary].warning }}</Badge>
            <Badge v-if="data.summary[kind as keyof typeof data.summary].critical" variant="critical" size="sm">{{ data.summary[kind as keyof typeof data.summary].critical }}</Badge>
            <Badge v-if="data.summary[kind as keyof typeof data.summary].unknown" variant="outline" size="sm">{{ data.summary[kind as keyof typeof data.summary].unknown }}</Badge>
          </span>
        </metric-card>
      </div>
    </div>

    <Card v-if="data?.issues?.length">
      <CardHeader><CardTitle>{{ $t('overview.issues') }}</CardTitle></CardHeader>
      <CardContent>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border">
                <th class="issue-th" style="width: 90px">{{ $t('overview.colLevel') }}</th>
                <th class="issue-th" style="width: 90px">{{ $t('overview.colType') }}</th>
                <th class="issue-th">{{ $t('overview.colResource') }}</th>
                <th class="issue-th">{{ $t('overview.colDetail') }}</th>
                <th class="issue-th" style="width: 150px">{{ $t('overview.colCheckedAt') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="i in data.issues" :key="i.kind + i.id" class="border-b border-border/60 hover:bg-accent/50">
                <td class="issue-td"><status-badge :status="i.status" /></td>
                <td class="issue-td">{{ KIND_META[i.kind] ? $t(`tabs.${i.kind}`) : i.kind }}</td>
                <td class="issue-td">{{ i.name }}</td>
                <td class="issue-td">{{ i.message }}</td>
                <td class="issue-td">{{ fmtTime(i.checked_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>

    <Card v-if="data">
      <CardHeader class="flex-row items-center justify-between">
        <CardTitle>{{ $t('overview.recentOps') }}</CardTitle>
        <Button variant="ghost" size="sm" @click="router.push('/audit')">{{ $t('overview.allLogs') }}</Button>
      </CardHeader>
      <CardContent>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border">
                <th class="issue-th" style="width: 130px">{{ $t('overview.colTime') }}</th>
                <th class="issue-th">{{ $t('overview.colResource') }}</th>
                <th class="issue-th">{{ $t('overview.colOperation') }}</th>
                <th class="issue-th">{{ $t('overview.colTarget') }}</th>
                <th class="issue-th" style="width: 90px">{{ $t('overview.colResult') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(op, idx) in data.recent_ops" :key="idx" class="border-b border-border/60 hover:bg-accent/50">
                <td class="issue-td">{{ fmtTime(op.time) }}</td>
                <td class="issue-td"><div class="ellip" :title="op.resource">{{ op.resource }}</div></td>
                <td class="issue-td">{{ op.operation }}</td>
                <td class="issue-td"><div class="mono ellip" :title="op.target ?? '-'">{{ op.target ?? '-' }}</div></td>
                <td class="issue-td">
                  <Badge :variant="op.result === 'SUCCESS' ? 'success' : 'critical'" size="sm">{{ op.result }}</Badge>
                </td>
              </tr>
              <tr v-if="!data.recent_ops.length">
                <td colspan="5" class="py-3 text-center text-muted-foreground">{{ $t('overview.noOps') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  </div>
</template>

<style scoped>
.ov-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ov-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ov-tiles {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.tile-wrap {
  flex: 1;
  min-width: 150px;
  cursor: pointer;
}
.dist {
  display: inline-flex;
  gap: 4px;
}
.mono {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
/* oplog 长值（redis key / 资源名）截断展示，title 悬浮看全量 */
.ellip {
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

<style>
/* 简表头/单元格（两处手写 table 共用）：padding 与 OpsDataTable 对齐 */
.issue-th {
  padding: 0.5rem 0.625rem;
  text-align: left;
  font-weight: 500;
  color: var(--muted-foreground);
  white-space: nowrap;
  font-size: 0.875rem;
}
.issue-td {
  padding: 0.5rem 0.625rem;
  vertical-align: middle;
  white-space: nowrap;
  font-size: 0.875rem;
}
</style>
