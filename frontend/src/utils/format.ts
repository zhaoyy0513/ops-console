/** 全站共用格式化工具（ui-upgrade-design.md §3.1：单一实现）。 */

export function pctColor(pct: number | null | undefined): string {
  if (pct == null) return 'var(--ops-unknown)'
  if (pct >= 90) return 'var(--ops-critical)'
  if (pct >= 80) return 'var(--ops-warning)'
  return 'var(--ops-healthy)'
}

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)}${units[i]}`
}

export function fmtMB(mb: number | null | undefined): string {
  if (mb == null) return '-'
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)}GB` : `${Math.round(mb)}MB`
}
