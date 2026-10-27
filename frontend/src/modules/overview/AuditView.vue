<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight, Search } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import OpsDataTable from '../../components/OpsDataTable.vue'
import { auditApi, type AuditPage } from './api'
import { opsUser, setOpsUser } from '../../lib/caller'

const { t } = useI18n()
const data = ref<AuditPage | null>(null)
const page = ref(1)
const size = 16
const loading = ref(false)

const callerDraft = ref(opsUser.value)

// 关键词搜索（服务端过滤，覆盖 cmd/target/operation/caller 全字段）
const searchDraft = ref('')
const searchQ = ref('')
let searchTimer: number | undefined
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = window.setTimeout(doSearch, 350)
}
function doSearch() {
  clearTimeout(searchTimer)
  searchQ.value = searchDraft.value.trim()
  page.value = 1
  load()
}
function saveCaller() {
  setOpsUser(callerDraft.value)
}

async function load() {
  loading.value = true
  try {
    data.value = await auditApi.page(page.value, size, searchQ.value)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function changePage(p: number) {
  page.value = p
  load()
}

const total = computed(() => data.value?.total ?? 0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

/** 最多 7 个页码：首末页常驻，两侧省略号折叠（页数 ≤7 全显） */
const pageItems = computed<Array<number | '…'>>(() => {
  const n = totalPages.value
  const cur = page.value
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const set = new Set<number>([1, n, cur - 1, cur, cur + 1])
  if (cur <= 3) { set.add(2); set.add(3) }
  if (cur >= n - 2) { set.add(n - 1); set.add(n - 2) }
  const pages = [...set].filter((p) => p >= 1 && p <= n).sort((a, b) => a - b)
  const out: Array<number | '…'> = []
  pages.forEach((p, i) => {
    if (i > 0 && p - pages[i - 1] > 1) out.push('…')
    out.push(p)
  })
  return out
})

type Row = NonNullable<AuditPage['items'][number]>

const columns = computed<any[]>(() => [
  // 时间列等宽字体 + tabular-nums：19 字符固定宽不折行（ISO 串字典序 = 时间序；服务端分页下仅当前页内排序）
  {
    accessorKey: 'time',
    header: t('audit.colTime'),
    sortDescFirst: false,
    cell: (ctx: any) =>
      h('span', { class: 'font-mono whitespace-nowrap tabular-nums' }, ((ctx.row.original as Row).time ?? '').replace('T', ' ').slice(0, 19)),
  },
  {
    accessorKey: 'site',
    header: t('audit.colSite'),
    sortDescFirst: false,
    cell: (ctx: any) => (ctx.row.original as Row).site,
  },
  {
    accessorKey: 'resource',
    header: t('audit.colResource'),
    sortDescFirst: false,
    cell: (ctx: any) => {
      const v = (ctx.row.original as Row).resource
      return h('span', { class: 'block max-w-[240px] truncate font-mono', title: v }, v)
    },
  },
  // 220px：最长操作 RESOURCE_CONFIG_DELETED（23 字符大写）单行不折行
  {
    accessorKey: 'operation',
    header: t('audit.colOperation'),
    sortDescFirst: false,
    cell: (ctx: any) => h('span', { class: 'whitespace-nowrap' }, (ctx.row.original as Row).operation),
  },
  {
    accessorKey: 'target',
    header: t('audit.colTarget'),
    sortDescFirst: false,
    cell: (ctx: any) => {
      const row = ctx.row.original as Row
      const v = row.target ?? '-'
      // 悬停可见执行内容（cmd 为命令前 200 字符）——"查谁跑了 rm -rf" 的关键信息
      const cmd = (row.params as any)?.cmd as string | undefined
      return h('span', { class: 'block max-w-[240px] truncate font-mono', title: cmd ? `${v}
${cmd}` : v }, v)
    },
  },
  {
    accessorKey: 'result',
    header: t('audit.colResult'),
    enableSorting: false,
    cell: (ctx: any) => {
      const row = ctx.row.original as Row
      const ok = row.result === 'SUCCESS'
      const risk = (row.params as any)?.risk as string[] | undefined
      if (risk?.length || row.result === 'BLOCKED') {
        return h('span', { class: 'inline-flex items-center gap-1' }, [
          h(Badge, { variant: 'warning', size: 'sm' }, { default: () => (risk?.length ? t('audit.riskConfirmed') : 'BLOCKED') }),
          h(Badge, { variant: ok ? 'success' : 'critical', size: 'sm' }, { default: () => row.result }),
        ])
      }
      return h(Badge, { variant: ok ? 'success' : 'critical', size: 'sm' }, { default: () => row.result })
    },
  },
  {
    id: 'caller',
    header: t('audit.colCaller'),
    enableSorting: false,
    cell: (ctx: any) => {
      const row = ctx.row.original as Row
      const who = row.caller && row.caller !== '-' ? row.caller : t('audit.anonymous')
      return h('span', { class: 'whitespace-nowrap', title: row.caller_ip }, [
        who,
        h('span', { class: 'ml-1.5 font-mono text-xs text-muted-foreground' }, row.caller_ip ?? '-'),
      ])
    },
  },
])
</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('audit.title') }}</CardTitle>
      <div class="flex items-center gap-3">
        <!-- 操作人别名：随请求头携带，oplog 溯源用（无用户管理下的轻量身份） -->
        <span class="flex items-center gap-1.5">
          <Search class="size-3.5 text-muted-foreground" />
          <input
            v-model="searchDraft"
            class="h-7 w-44 rounded-md border border-input bg-card px-2 text-xs outline-none focus:border-ring"
            :placeholder="$t('audit.searchPh')"
            @input="onSearchInput"
            @keyup.enter="doSearch"
          />
        </span>
        <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
          {{ $t('audit.callerLabel') }}
          <input
            v-model="callerDraft"
            class="h-7 w-28 rounded-md border border-input bg-card px-2 text-xs outline-none focus:border-ring"
            :placeholder="$t('audit.callerPh')"
            @change="saveCaller"
          />
        </span>
        <span class="text-xs text-muted-foreground">{{ $t('audit.hint') }}</span>
      </div>
    </CardHeader>
    <CardContent>
      <!-- 列宽合计约 900：窄屏时表格内部横向滚动（OpsDataTable 自带 overflow-auto），而不是把页面撑宽 -->
      <OpsDataTable
        class="min-w-[1080px]"
        :columns="columns"
        :data="data?.items ?? []"
        :empty-text="$t('overview.noOps')"
        :mono="false"
      >
        <template #empty>
          <span v-if="loading" class="inline-block size-5 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
          <template v-else>—</template>
        </template>
      </OpsDataTable>
      <div class="mt-3 flex justify-end items-center gap-1">
        <Button variant="outline" size="icon-sm" :disabled="page <= 1 || loading" @click="changePage(page - 1)">
          <ChevronLeft />
        </Button>
        <template v-for="(p, i) in pageItems" :key="`${p}-${i}`">
          <span v-if="p === '…'" class="px-1 text-muted-foreground">…</span>
          <Button
            v-else
            :variant="p === page ? 'default' : 'outline'"
            size="icon-sm"
            class="font-mono"
            :disabled="loading"
            @click="changePage(p)"
          >
            {{ p }}
          </Button>
        </template>
        <Button variant="outline" size="icon-sm" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">
          <ChevronRight />
        </Button>
      </div>
    </CardContent>
  </Card>
</template>
