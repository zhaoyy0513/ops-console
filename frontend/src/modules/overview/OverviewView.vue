<script setup lang="ts">
import { onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  HardwareChipOutline, LayersOutline, PulseOutline, ServerOutline,
} from '@vicons/ionicons5'
import { NButton, NCard, NTable, NTag, useMessage } from 'naive-ui'
import StatusBadge from '../../components/StatusBadge.vue'
import TabHelp from '../../components/TabHelp.vue'
import MetricCard from '../../components/MetricCard.vue'
import { useSiteStore } from '../../stores/site'
import { overviewApi, type OverviewData } from './api'

const siteStore = useSiteStore()
const router = useRouter()
const message = useMessage()

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
  server: { label: 'Server', route: 'server', icon: ServerOutline },
  redis: { label: 'Redis', route: 'redis', icon: LayersOutline },
  mq: { label: 'ActiveMQ', route: 'mq', icon: PulseOutline },
  robot: { label: 'Robot', route: 'robot', icon: HardwareChipOutline },
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
    <n-card size="small">
      <div class="ov-bar">
        <span style="font-size: 16px; font-weight: 600">{{ data?.site.name ?? siteStore.currentSiteId }}</span>
        <status-badge v-if="data" :status="data.overall" />
        <n-button size="small" :loading="loading" @click="refresh">{{ $t('overview.checkNow') }}</n-button>
        <tab-help topic="overview" />
        <span v-if="data?.checked_at" style="color: var(--ops-text-3); font-size: 12px">
          {{ $t('overview.lastCheck', { time: fmtTime(data.checked_at) }) }}
        </span>
      </div>
    </n-card>

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
            <n-tag type="success" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].healthy }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].warning" type="warning" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].warning }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].critical" type="error" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].critical }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].unknown" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].unknown }}</n-tag>
          </span>
        </metric-card>
      </div>
    </div>

    <n-card v-if="data?.issues?.length" size="small" :title="$t('overview.issues')">
      <div class="table-scroll">
        <n-table :single-line="false" size="small">
        <thead>
          <tr><th style="width: 90px">{{ $t('overview.colLevel') }}</th><th style="width: 90px">{{ $t('overview.colType') }}</th><th>{{ $t('overview.colResource') }}</th><th>{{ $t('overview.colDetail') }}</th><th style="width: 150px">{{ $t('overview.colCheckedAt') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="i in data.issues" :key="i.kind + i.id">
            <td><status-badge :status="i.status" /></td>
            <td>{{ KIND_META[i.kind] ? $t(`tabs.${i.kind}`) : i.kind }}</td>
            <td>{{ i.name }}</td>
            <td>{{ i.message }}</td>
            <td>{{ fmtTime(i.checked_at) }}</td>
          </tr>
        </tbody>
      </n-table>
      </div>
    </n-card>

    <n-card v-if="data" size="small" :title="$t('overview.recentOps')">
      <template #header-extra>
        <n-button size="tiny" quaternary @click="router.push('/audit')">{{ $t('overview.allLogs') }}</n-button>
      </template>
      <div class="table-scroll">
        <n-table :single-line="false" size="small">
        <thead>
          <tr><th style="width: 130px">{{ $t('overview.colTime') }}</th><th>{{ $t('overview.colResource') }}</th><th>{{ $t('overview.colOperation') }}</th><th>{{ $t('overview.colTarget') }}</th><th style="width: 90px">{{ $t('overview.colResult') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(op, idx) in data.recent_ops" :key="idx">
            <td>{{ fmtTime(op.time) }}</td>
            <td><div class="ellip" :title="op.resource">{{ op.resource }}</div></td>
            <td>{{ op.operation }}</td>
            <td><div class="mono ellip" :title="op.target ?? '-'">{{ op.target ?? '-' }}</div></td>
            <td>
              <n-tag :type="op.result === 'SUCCESS' ? 'success' : 'error'" size="tiny" :bordered="false">{{ op.result }}</n-tag>
            </td>
          </tr>
          <tr v-if="!data.recent_ops.length">
            <td colspan="5" style="text-align: center; color: var(--ops-text-3)">{{ $t('overview.noOps') }}</td>
          </tr>
        </tbody>
      </n-table>
      </div>
    </n-card>
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
/* 表格内部横向滚动，不撑破页面 */
.table-scroll {
  overflow-x: auto;
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
