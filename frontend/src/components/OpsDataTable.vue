<script setup lang="ts" generic="T extends Record<string, any>">
/** 全站统一表格：TanStack Table v9 核心 + Tailwind 自绘（shadcn data-table 规格）。
    模块代码只给 columns + data，样式/密度/空态/排序 UI 在这里。 */
import { FlexRender, useTable } from '@tanstack/vue-table'
import {
  createCoreRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
  type SortingState,
} from '@tanstack/table-core'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Inbox } from 'lucide-vue-next'
import { computed, markRaw, ref, watch, type Component } from 'vue'
import { cn } from '@/lib/utils'

/** 排序指示：asc ↑ / desc ↓ / 未排序 ⇅（对象引用防 resolve 警告） */
const ARROW_UP = markRaw(ArrowUp) as Component
const ARROW_DOWN = markRaw(ArrowDown) as Component
const ARROW_BOTH = markRaw(ArrowUpDown) as Component
function sortIcon(column: any): Component {
  const s = column.getIsSorted()
  return s === 'asc' ? ARROW_UP : s === 'desc' ? ARROW_DOWN : ARROW_BOTH
}

const props = defineProps<{
  columns: any[] // ColumnDef 推断在 generic + features 组合下易碎，模块侧以 duck type 传入
  data: T[]
  /** 行 key 取值字段（稳定 diff） */
  rowKey?: string
  /** 无数据文案 */
  emptyText?: string
  /** 密度：compact 用于 metrics/进程表 */
  size?: 'default' | 'compact'
  /** 单元格/表头等宽字体（terminal 风格外也用于数字列） */
  mono?: boolean
  /** 每页行数：传入即启用客户端分页（大表必备——几千行 × 每行组件会打爆渲染） */
  pageSize?: number
}>()

const sorting = ref<SortingState>([])
const pageIndex = ref(0)

// 分页仅在显式传 pageSize 时注册（小表无分页条）
const features = tableFeatures(
  props.pageSize
    ? ({ rowSortingFeature, rowPaginationFeature, sortedRowModel: createSortedRowModel(), paginatedRowModel: createPaginatedRowModel(), sortFns: { alphanumeric: sortFn_alphanumeric } } as any)
    : ({ rowSortingFeature, sortedRowModel: createSortedRowModel(), sortFns: { alphanumeric: sortFn_alphanumeric } } as any),
)

const table = useTable({
  features,
  data: computed(() => props.data),
  columns: computed(() => props.columns as any),
  state: {
    get sorting() { return sorting.value },
    ...(props.pageSize ? { get pagination() { return { pageIndex: pageIndex.value, pageSize: props.pageSize! } } } : {}),
  },
  onSortingChange: (updater: any) => {
    sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater
  },
  getCoreRowModel: createCoreRowModel(),
  getSortedRowModel: createSortedRowModel(),
  ...(props.pageSize ? { getPaginatedRowModel: createPaginatedRowModel() } : {}),
} as any)

// 数据源变化时回到第一页（轮询刷新/重查保持可预期）
watch(() => props.data, () => { pageIndex.value = 0 })

const pageRows = computed(() => table.getRowModel().rows)
const pageCount = computed(() => (props.pageSize ? table.getPageCount() : 1))

// 行密度：default 常规数据表 / compact 指标与进程表
const cellPy = computed(() => (props.size === 'compact' ? 'py-1.5' : 'py-2.5'))
const rowClasses = computed(() => (props.size === 'compact' ? 'h-8' : 'h-11'))
</script>

<template>
  <div class="relative w-full overflow-x-auto">
    <table class="w-full caption-bottom border-collapse text-[13px]">
      <thead>
        <tr
          v-for="headerGroup in table.getHeaderGroups()"
          :key="headerGroup.id"
          class="border-b border-border bg-muted/40"
        >
          <th
            v-for="(header, i) in headerGroup.headers"
            :key="header.id"
            :class="
              cn(
                'h-9 whitespace-nowrap px-3 text-left align-middle text-xs font-medium text-muted-foreground select-none',
                i === 0 && 'pl-4',
                header.column.getCanSort() && 'cursor-pointer transition-colors hover:text-foreground',
                props.mono && 'font-mono',
              )
            "
            @click="header.column.getCanSort() && header.column.toggleSorting()"
          >
            <span class="group/th inline-flex items-center gap-1.5">
              <FlexRender v-if="!header.isPlaceholder" :render="header.column.columnDef.header" :props="header.getContext()" />
              <!-- 图标用 :is 组件对象引用（非字符串标签），杜绝 resolveComponent 类警告 -->
              <component
                :is="sortIcon(header.column)"
                :class="
                  cn(
                    'size-3.5 transition-colors',
                    header.column.getIsSorted() ? 'text-primary' : 'text-muted-foreground/40 group-hover/th:text-muted-foreground',
                  )
                "
              />
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in pageRows"
          :key="rowKey ? (row.original as any)[rowKey] ?? row.id : row.id"
          :class="cn('border-b border-border/70 transition-colors last:border-0 hover:bg-muted/50', rowClasses)"
        >
          <td
            v-for="(cell, i) in row.getAllCells()"
            :key="cell.id"
            :class="
              cn(
                'align-middle whitespace-nowrap px-3 text-foreground',
                cellPy,
                i === 0 && 'pl-4',
                props.mono && 'font-mono',
              )
            "
          >
            <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
          </td>
        </tr>
        <tr v-if="pageRows.length === 0">
          <td :colspan="table.getAllLeafColumns().length" class="h-32 text-center text-[13px] text-muted-foreground">
            <div class="flex flex-col items-center justify-center gap-2">
              <Inbox class="size-8 opacity-30" :stroke-width="1.5" />
              <slot name="empty">{{ emptyText ?? '—' }}</slot>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <!-- 分页条：仅大表启用（pageSize 传入时） -->
    <div
      v-if="props.pageSize && pageCount > 1"
      class="flex items-center justify-end gap-3 border-t border-border px-4 py-2 text-xs text-muted-foreground"
    >
      <span>{{ pageIndex + 1 }} / {{ pageCount }}</span>
      <div class="flex items-center gap-1">
        <button
          class="inline-flex size-7 items-center justify-center rounded-md transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
          :disabled="!table.getCanPreviousPage()"
          @click="table.previousPage()"
        >
          <ChevronLeft class="size-4" />
        </button>
        <button
          class="inline-flex size-7 items-center justify-center rounded-md transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
          :disabled="!table.getCanNextPage()"
          @click="table.nextPage()"
        >
          <ChevronRight class="size-4" />
        </button>
      </div>
    </div>
  </div>
</template>
