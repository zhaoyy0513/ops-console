import api from '../../api'

export interface OverviewData {
  site: { id: string; name: string; description: string; enabled: boolean }
  overall: 'HEALTHY' | 'WARNING' | 'CRITICAL'
  summary: Record<
    'server' | 'redis' | 'mq' | 'device',
    { total: number; healthy: number; warning: number; critical: number; unknown: number }
  >
  issues: Array<{ kind: string; id: string; name: string; status: string; message: string; checked_at: string }>
  recent_ops: Array<{
    time: string
    site: string
    resource: string
    operation: string
    target: string | null
    result: string
    /** 操作人别名（无 HTTP 上下文时为 "-"） */
    caller?: string
  }>
  checked_at: string | null
}

export const overviewApi = {
  get: (siteId: string) => api.get<OverviewData>(`/sites/${siteId}/overview`),
  refresh: (siteId: string) => api.post<{ checked: number }>(`/sites/${siteId}/overview/refresh`),
}

export interface SamplePoint {
  ts: number
  v: number
}

/** 趋势采样序列（rid 形如 server:s1 / redis:r1 / <mq_id>，新->旧） */
export function getSamples(rid: string, series: string, limit = 60): Promise<SamplePoint[]> {
  return api.get(`/samples?rid=${encodeURIComponent(rid)}&series=${encodeURIComponent(series)}&limit=${limit}`)
}

export interface AuditPage {
  items: Array<{
    time: string
    site: string
    resource: string
    operation: string
    target: string | null
    params: Record<string, unknown> | null
    result: string
    error: string | null
    // 调用者溯源（2026-10-23）：定时任务等无 HTTP 上下文路径为 "-"
    caller: string
    caller_ip: string
  }>
  total: number
}

export const auditApi = {
  page: (page = 1, size = 50, q = '') => api.get<AuditPage>(`/audit?page=${page}&size=${size}${q ? `&q=${encodeURIComponent(q)}` : ''}`),
}
