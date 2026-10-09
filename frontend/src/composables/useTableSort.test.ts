import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useTableSort } from './useTableSort'

describe('useTableSort', () => {
  it('cycles none -> asc -> desc -> none', () => {
    const rows = ref([{ n: 3 }, { n: 1 }, { n: 2 }])
    const { sortKey, sortDir, sortedRows, toggleSort } = useTableSort(rows, (r, k) => (r as Record<string, unknown>)[k])

    expect(sortedRows.value.map((r) => r.n)).toEqual([3, 1, 2]) // 未排序 = 原序

    toggleSort('n')
    expect(sortKey.value).toBe('n')
    expect(sortDir.value).toBe('asc')
    expect(sortedRows.value.map((r) => r.n)).toEqual([1, 2, 3])

    toggleSort('n')
    expect(sortDir.value).toBe('desc')
    expect(sortedRows.value.map((r) => r.n)).toEqual([3, 2, 1])

    toggleSort('n')
    expect(sortKey.value).toBeNull()
    expect(sortedRows.value.map((r) => r.n)).toEqual([3, 1, 2])
  })

  it('numeric strings compare numerically; null/empty always last in both directions', () => {
    const rows = ref([{ v: '10' }, { v: '9' }, { v: null }, { v: '' }])
    const { sortedRows, toggleSort } = useTableSort(rows, (r, k) => (r as Record<string, unknown>)[k])

    toggleSort('v')
    expect(sortedRows.value.map((r) => r.v)).toEqual(['9', '10', null, '']) // 空值类（null/''）恒在尾，彼此保持原序
    toggleSort('v')
    expect(sortedRows.value.map((r) => r.v)).toEqual(['10', '9', null, '']) // 降序空值仍在尾
  })

  it('equal keys keep original order (stable copy, source array untouched)', () => {
    const rows = ref([{ g: 1, id: 'a' }, { g: 1, id: 'b' }, { g: 0, id: 'c' }])
    const { sortedRows, toggleSort } = useTableSort(rows, (r, k) => (r as Record<string, unknown>)[k])

    toggleSort('g')
    expect(sortedRows.value.map((r) => r.id)).toEqual(['c', 'a', 'b'])
    expect(rows.value.map((r) => r.id)).toEqual(['a', 'b', 'c']) // 原数组不动
  })
})
