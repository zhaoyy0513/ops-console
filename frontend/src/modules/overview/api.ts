import api from '../../api'

export interface OverviewData {
  site: { id: string; name: string; description: string; enabled: boolean }
  overall: 'HEALTHY' | 'WARNING' | 'CRITICAL'
  summary: Record<
    'server' | 'redis' | 'mq' | 'robot',
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
  }>
  checked_at: string | null
}

export const overviewApi = {
  get: (siteId: string) => api.get<OverviewData>(`/sites/${siteId}/overview`),
  refresh: (siteId: string) => api.post<{ checked: number }>(`/sites/${siteId}/overview/refresh`),
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
  }>
  total: number
}

export const auditApi = {
  page: (page = 1, size = 50) => api.get<AuditPage>(`/audit?page=${page}&size=${size}`),
}
