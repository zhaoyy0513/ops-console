<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NSpace, NTable, NTag, useMessage } from 'naive-ui'
import StatusBadge from '../../components/StatusBadge.vue'
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

const KIND_META: Record<string, { label: string; route: string }> = {
  server: { label: 'Server', route: 'server' },
  redis: { label: 'Redis', route: 'redis' },
  mq: { label: 'ActiveMQ', route: 'mq' },
  robot: { label: 'Robot', route: 'robot' },
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
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12">
        <span style="font-size: 16px; font-weight: 600">{{ data?.site.name ?? siteStore.currentSiteId }}</span>
        <status-badge v-if="data" :status="data.overall" />
        <n-button size="small" :loading="loading" @click="refresh">立即检查</n-button>
        <span v-if="data?.checked_at" style="color: #999; font-size: 12px">
          上次检查 {{ fmtTime(data.checked_at) }}（后台每 30 秒）
        </span>
      </n-space>
    </n-card>

    <n-space v-if="data" :size="12">
      <n-card v-for="(meta, kind) in KIND_META" :key="kind" size="small"
        :title="meta.label" style="flex: 1; cursor: pointer" @click="goIssueModule(kind)">
        <div class="tile">
          <span class="total">{{ data.summary[kind as keyof typeof data.summary].total }}</span>
          <span class="dist">
            <n-tag type="success" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].healthy }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].warning" type="warning" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].warning }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].critical" type="error" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].critical }}</n-tag>
            <n-tag v-if="data.summary[kind as keyof typeof data.summary].unknown" size="tiny" :bordered="false">{{ data.summary[kind as keyof typeof data.summary].unknown }}</n-tag>
          </span>
        </div>
      </n-card>
    </n-space>

    <n-card v-if="data?.issues?.length" size="small" title="异常摘要">
      <n-table :single-line="false" size="small">
        <thead>
          <tr><th style="width: 90px">级别</th><th style="width: 90px">类型</th><th>资源</th><th>详情</th><th style="width: 150px">检查时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="i in data.issues" :key="i.kind + i.id">
            <td><status-badge :status="i.status" /></td>
            <td>{{ KIND_META[i.kind]?.label ?? i.kind }}</td>
            <td>{{ i.name }}</td>
            <td>{{ i.message }}</td>
            <td>{{ fmtTime(i.checked_at) }}</td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <n-card v-if="data" size="small" title="最近操作">
      <template #header-extra>
        <n-button size="tiny" quaternary @click="router.push('/audit')">全部日志</n-button>
      </template>
      <n-table :single-line="false" size="small">
        <thead>
          <tr><th style="width: 130px">时间</th><th>资源</th><th>操作</th><th>目标</th><th style="width: 90px">结果</th></tr>
        </thead>
        <tbody>
          <tr v-for="(op, idx) in data.recent_ops" :key="idx">
            <td>{{ fmtTime(op.time) }}</td>
            <td>{{ op.resource }}</td>
            <td>{{ op.operation }}</td>
            <td style="font-family: ui-monospace, monospace">{{ op.target ?? '-' }}</td>
            <td>
              <n-tag :type="op.result === 'SUCCESS' ? 'success' : 'error'" size="tiny" :bordered="false">{{ op.result }}</n-tag>
            </td>
          </tr>
          <tr v-if="!data.recent_ops.length">
            <td colspan="5" style="text-align: center; color: #999">暂无操作记录</td>
          </tr>
        </tbody>
      </n-table>
    </n-card>
  </n-space>
</template>

<style scoped>
.tile {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.total {
  font-size: 28px;
  font-weight: 600;
}
.dist {
  display: flex;
  gap: 4px;
}
</style>
