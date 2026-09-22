import api from '../../api'

export interface MqOverview {
  name: string | null
  status: string
  version: string | null
  uptime: string | null
  connections: number | null
  total_connections: number | null
  sessions: number | null
  consumers: number | null
  producers: number | null
  addresses: number | null
  jvm: {
    heap_used: number | null
    heap_max: number | null
    non_heap_used: number | null
    threads: number | null
    gc: Array<{ name: string; count: number | null; time_ms: number | null }>
  }
}

export interface QueueRow {
  name: string
  address: string | null
  routing_type: string | null
  message_count: number | null
  consumer_count: number | null
  delivering_count: number | null
  messages_added: number | null
  messages_acknowledged: number | null
  backlog_5m_ago: number | null
  growth_5m: number | null
  /** 完整 ObjectName（清空积压等管理操作用，由后端校验） */
  _mbean?: string
  diagnosis: { status: string; issues: Array<{ type: string; severity: string; message: string }> }
}

export interface AddressRow {
  name: string
  message_count: number | null
  consumer_count: number | null
  producer_count: number | null
  address_size: number | null
}

export const mqApi = {
  overview: (siteId: string, id: string) => api.get<MqOverview>(`/sites/${siteId}/mq/${id}/overview`),
  queues: (siteId: string, id: string) => api.get<QueueRow[]>(`/sites/${siteId}/mq/${id}/queues`),
  addresses: (siteId: string, id: string) => api.get<AddressRow[]>(`/sites/${siteId}/mq/${id}/addresses`),
  /** 清空队列积压消息（危险操作，前端倒计时确认 + 后端记录操作日志） */
  emptyQueue: (siteId: string, id: string, mbean: string, queue: string) =>
    api.post<{ success: boolean; latency_ms: number }>(`/sites/${siteId}/mq/${id}/queues/empty`, {
      mbean,
      queue,
    }),
}
