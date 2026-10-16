import api from '../../api'

/** 页面资源：外链 或 内联 HTML 二选一（资源 CRUD 走 sites 通用接口） */
export interface PageResource {
  id: string
  name: string
  description: string
  /** 读取时派生：有 url 即 "url"，否则 "html"；老数据同样自动分类 */
  kind: 'url' | 'html' | null
  url?: string | null
  html?: string | null
  enabled?: boolean
}

export const pageApi = {
  /** 当前站点的全部页面配置（站点级资源，无 instance 维度） */
  list: (siteId: string) => api.get<PageResource[]>(`/sites/${siteId}/pages`),
}
