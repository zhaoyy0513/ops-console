import api from '../../api'

export interface Site {
  id: string
  name: string
  description: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type ResourceConfig = {
  id: string
  name: string
  enabled: boolean
  password?: string
  [key: string]: unknown
}

export type ResourceType = 'servers' | 'redis' | 'mq' | 'robots'

/** 资源路由类型 -> 连接测试类型（PRD §13：server|redis|mq|robot） */
export const TEST_TYPE: Record<ResourceType, string> = {
  servers: 'server',
  redis: 'redis',
  mq: 'mq',
  robots: 'robot',
}

export const sitesApi = {
  list: () => api.get<Site[]>('/sites'),
  get: (id: string) => api.get<Site>(`/sites/${id}`),
  create: (data: Partial<Site>) => api.post<Site>('/sites', data),
  update: (id: string, data: Partial<Site>) => api.put<Site>(`/sites/${id}`, data),
  remove: (id: string) => api.delete<void>(`/sites/${id}`),

  listResources: (siteId: string, type: ResourceType) =>
    api.get<ResourceConfig[]>(`/sites/${siteId}/${type}`),
  createResource: (siteId: string, type: ResourceType, data: Record<string, unknown>) =>
    api.post<ResourceConfig>(`/sites/${siteId}/${type}`, data),
  updateResource: (
    siteId: string,
    type: ResourceType,
    id: string,
    data: Record<string, unknown>,
  ) => api.put<ResourceConfig>(`/sites/${siteId}/${type}/${id}`, data),
  removeResource: (siteId: string, type: ResourceType, id: string) =>
    api.delete<void>(`/sites/${siteId}/${type}/${id}`),
}
