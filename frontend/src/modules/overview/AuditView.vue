<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NCard, NDataTable, NPagination, NSpace, NTag } from 'naive-ui'
import { auditApi, type AuditPage } from './api'

const data = ref<AuditPage | null>(null)
const page = ref(1)
const size = 50
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await auditApi.page(page.value, size)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function changePage(p: number) {
  page.value = p
  load()
}

type Row = NonNullable<AuditPage['items'][number]>

const columns = [
  { title: '时间', key: 'time', width: 170, render: (row: Row) => (row.time ?? '').replace('T', ' ').slice(0, 19) },
  { title: '站点', key: 'site', width: 120 },
  { title: '资源', key: 'resource', width: 180 },
  { title: '操作', key: 'operation', width: 220 },
  {
    title: '目标',
    key: 'target',
    render: (row: Row) => row.target ?? '-',
  },
  {
    title: '结果',
    key: 'result',
    width: 100,
    render: (row: Row) =>
      h(NTag, { type: row.result === 'SUCCESS' ? 'success' : 'error', size: 'small', bordered: false }, { default: () => row.result }),
  },
]
</script>

<template>
  <n-card title="操作日志" size="small">
    <template #header-extra>
      <span style="color: #999; font-size: 12px">仅保留最近 1000 条 · 无用户维度（PRD §17）</span>
    </template>
    <n-data-table :columns="columns" :data="data?.items ?? []" :loading="loading"
      :row-key="(row: Record<string, unknown>) => String(row.time) + String(row.operation)" size="small" :bordered="false" :single-line="false" />
    <n-space justify="end" style="margin-top: 12px">
      <n-pagination :page="page" :page-size="size" :item-count="data?.total ?? 0"
        @update:page="changePage" />
    </n-space>
  </n-card>
</template>