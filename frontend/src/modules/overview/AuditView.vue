<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NCard, NDataTable, NPagination, NSpace, NTag } from 'naive-ui'
import { auditApi, type AuditPage } from './api'

const { t } = useI18n()
const data = ref<AuditPage | null>(null)
const page = ref(1)
const size = 16
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

const columns = computed(() => [
  // 时间列固定宽 + 禁止换行：'2026-09-29 16:20:33' 必须单行（换行两行太高）
  { title: t('audit.colTime'), key: 'time', width: 170, className: 'nowrap', render: (row: Row) => (row.time ?? '').replace('T', ' ').slice(0, 19) },
  { title: t('audit.colSite'), key: 'site', width: 120 },
  { title: t('audit.colResource'), key: 'resource', width: 170, className: 'mono', ellipsis: { tooltip: true } },
  // 180px：最长常见操作 RESOURCE_CONFIG_DELETED / SERVER_KILL_ZOMBIE 单行放得下
  { title: t('audit.colOperation'), key: 'operation', width: 180 },
  {
    title: t('audit.colTarget'),
    key: 'target',
    minWidth: 120,
    className: 'mono',
    ellipsis: { tooltip: true },
    render: (row: Row) => row.target ?? '-',
  },
  {
    title: t('audit.colResult'),
    key: 'result',
    width: 90,
    render: (row: Row) =>
      h(NTag, { type: row.result === 'SUCCESS' ? 'success' : 'error', size: 'small', bordered: false }, { default: () => row.result }),
  },
])
</script>

<template>
  <n-card :title="$t('audit.title')" size="small">
    <template #header-extra>
      <span style="color: #999; font-size: 12px">{{ $t('audit.hint') }}</span>
    </template>
    <n-data-table class="audit-table" :columns="columns" :data="data?.items ?? []" :loading="loading"
      :row-key="(row: Record<string, unknown>) => String(row.time) + String(row.operation)" size="small" :bordered="false" :single-line="false" />
    <n-space justify="end" style="margin-top: 12px">
      <n-pagination :page="page" :page-size="size" :item-count="data?.total ?? 0"
        @update:page="changePage" />
    </n-space>
  </n-card>
</template>

<!-- 非 scoped：数据表格 render 单元格吃不到 scoped 属性，按 .audit-table 收窄 -->
<style>
.audit-table td.mono {
  font-family: var(--ops-font-mono);
}
.audit-table td.nowrap {
  white-space: nowrap;
}
</style>