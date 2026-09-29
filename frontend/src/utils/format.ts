/** 全站共用格式化工具（ui-upgrade-design.md §3.1：单一实现）。 */

/** 百分比 → 语义色。返回 hex（非 var()）：ECharts canvas 解析不了 CSS 变量。
 *  所选值在亮/暗两种底色上对比度均可接受，无需双份。 */
export function pctColor(pct: number | null | undefined): string {
  if (pct == null) return '#909399'
  if (pct >= 90) return '#d03050'
  if (pct >= 80) return '#f0a020'
  return '#18a058'
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
