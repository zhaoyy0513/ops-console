/** knowledge 条目表单 → 提交 payload。三选一校验 + 空内容字段剔除
 *  （html/markdown 空串不提交——后端 update 是提交即覆盖，漏过滤会抹掉文档内容）。 */
export function prepareKnowledgeData(form: Record<string, any>): { error?: string; data?: Record<string, unknown> } {
  const name = String(form.name ?? '').trim()
  if (!name) return { error: 'nameRequired' }
  const data: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(form)) {
    if (v === null || v === undefined) continue
    if (typeof v === 'string' && !v.trim() && (k === 'html' || k === 'markdown')) continue
    data[k] = v
  }
  const has = (k: string) => String(data[k] ?? '').trim() !== ''
  if (!has('url') && !has('markdown') && !has('html')) return { error: 'needOne' }
  return { data: { ...data, name } }
}
