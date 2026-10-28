import api from '../../api'

/** 页面资源：外链（url）或 内联 HTML（html）二选一。kind 后端读取时派生：url > html。 */
export interface PageResource {
  id: string
  name: string
  description: string
  kind: 'url' | 'html' | null
  url?: string | null
  html?: string | null
  enabled?: boolean
}

export const pageApi = {
  list: (siteId: string) => api.get<PageResource[]>(`/sites/${siteId}/pages`),
  create: (siteId: string, data: Record<string, unknown>) =>
    api.post<PageResource>(`/sites/${siteId}/pages`, data),
  update: (siteId: string, id: string, data: Record<string, unknown>) =>
    api.put<PageResource>(`/sites/${siteId}/pages/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/sites/${siteId}/pages/${id}`),
}

/** 与后端 kind 派生同规则（url > html）的客户端镜像，供视图/测试共用 */
export function derivePageKind(item: Pick<PageResource, 'url' | 'html'>): PageResource['kind'] {
  return item.url ? 'url' : item.html ? 'html' : null
}
