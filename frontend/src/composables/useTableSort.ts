import { computed, ref, type Ref } from 'vue'

export type SortDir = 'asc' | 'desc'

/**
 * 手写表格的当前页客户端排序（NDataTable 用自带 sorter，不走这里）。
 *
 * toggleSort(key)：未排序 -> 升序 -> 降序 -> 未排序（单列生效，换列重新升序）。
 * sortedRows：排序副本（stable，等值保持原序），未排序时原样返回；
 * null/undefined/'' 恒排末尾（升序降序一致）；两侧都能 Number() 时按数值比，
 * 否则按字符串 localeCompare（同列取值类型一致时行为确定）。
 */
export function useTableSort<T>(
  rows: Ref<T[]>,
  getValue: (row: T, key: string) => unknown,
) {
  const sortKey = ref<string | null>(null)
  const sortDir = ref<SortDir | null>(null)

  function toggleSort(key: string) {
    if (sortKey.value !== key) {
      sortKey.value = key
      sortDir.value = 'asc'
    } else if (sortDir.value === 'asc') {
      sortDir.value = 'desc'
    } else {
      sortKey.value = null
      sortDir.value = null
    }
  }

  const sortedRows = computed(() => {
    const key = sortKey.value
    const dir = sortDir.value
    if (!key || !dir) return rows.value
    const sign = dir === 'asc' ? 1 : -1
    return [...rows.value].sort((a, b) => {
      const va = getValue(a, key)
      const vb = getValue(b, key)
      const ea = va == null || va === ''
      const eb = vb == null || vb === ''
      if (ea || eb) return ea && eb ? 0 : ea ? 1 : -1 // 空值恒末尾，不随方向翻转
      const na = Number(va)
      const nb = Number(vb)
      if (!Number.isNaN(na) && !Number.isNaN(nb)) return (na - nb) * sign
      return String(va).localeCompare(String(vb)) * sign
    })
  })

  return { sortKey, sortDir, sortedRows, toggleSort }
}
