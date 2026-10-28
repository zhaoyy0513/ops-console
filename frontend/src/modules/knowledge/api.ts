import api from '../../api'

/** 知识库资源：链接（url）/ Markdown 文档（markdown）/ HTML 页（html）三选一。
 *  kind 读取时由后端派生：url > markdown > html。 */
export interface KnowledgeResource {
  id: string
  name: string
  description: string
  kind: 'url' | 'markdown' | 'html' | null
  url?: string | null
  markdown?: string | null
  html?: string | null
  enabled?: boolean
}

export const knowledgeApi = {
  list: (siteId: string) => api.get<KnowledgeResource[]>(`/sites/${siteId}/knowledge`),
  create: (siteId: string, data: Record<string, unknown>) =>
    api.post<KnowledgeResource>(`/sites/${siteId}/knowledge`, data),
  update: (siteId: string, id: string, data: Record<string, unknown>) =>
    api.put<KnowledgeResource>(`/sites/${siteId}/knowledge/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/sites/${siteId}/knowledge/${id}`),
}

/** 与后端 kind 派生同规则（url > markdown > html）的客户端镜像，供视图/测试共用 */
export function deriveKind(item: Pick<KnowledgeResource, 'url' | 'markdown' | 'html'>): KnowledgeResource['kind'] {
  return item.url ? 'url' : item.markdown ? 'markdown' : item.html ? 'html' : null
}
