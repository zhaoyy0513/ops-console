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

export type ResourceType = 'servers' | 'pages' | 'redis' | 'mq' | 'devices'

/** 资源实例 CRUD 的 URL 段（devices 让位给业务路由 /devices，存储 key 同名） */
export const URL_SEGMENT: Record<ResourceType, string> = {
  servers: 'servers',
  pages: 'pages',
  redis: 'redis',
  mq: 'mq',
  devices: 'device-instances',
}

/** 资源路由类型 -> 连接测试类型（server|redis|mq|device）；pages 无连接测试 */
export const TEST_TYPE: Partial<Record<ResourceType, string>> = {
  servers: 'server',
  redis: 'redis',
  mq: 'mq',
  devices: 'device',
}

function resUrl(siteId: string, type: ResourceType): string {
  return `/sites/${siteId}/${URL_SEGMENT[type]}`
}

export const sitesApi = {
  list: () => api.get<Site[]>('/sites'),
  get: (id: string) => api.get<Site>(`/sites/${id}`),
  create: (data: Partial<Site>) => api.post<Site>('/sites', data),
  update: (id: string, data: Partial<Site>) => api.put<Site>(`/sites/${id}`, data),
  remove: (id: string) => api.delete<void>(`/sites/${id}`),

  listResources: (siteId: string, type: ResourceType) =>
    api.get<ResourceConfig[]>(resUrl(siteId, type)),
  createResource: (siteId: string, type: ResourceType, data: Record<string, unknown>) =>
    api.post<ResourceConfig>(resUrl(siteId, type), data),
  updateResource: (siteId: string, type: ResourceType, id: string, data: Record<string, unknown>) =>
    api.put<ResourceConfig>(`${resUrl(siteId, type)}/${id}`, data),
  removeResource: (siteId: string, type: ResourceType, id: string) =>
    api.delete<void>(`${resUrl(siteId, type)}/${id}`),
}
