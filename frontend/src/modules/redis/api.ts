import api from '../../api'

export interface RedisInfo {
  status: string
  version: string | null
  uptime_seconds: number
  memory_used: number
  memory_peak: number
  memory_fragmentation: number | null
  connected_clients: number
  commands_per_sec: number | null
  total_commands_processed: number
  hit_rate: number | null
  evicted_keys: number
  expired_keys: number
  db_size: number
}

export interface KeyItem {
  key: string
  type: string
}

export interface KeyDetail {
  key: string
  type: 'string' | 'hash' | 'list' | 'set' | 'zset'
  ttl: number // 秒；-1 无过期；-2 不存在
  memory_usage: number | null
  value: unknown
}

export interface KeysPage {
  keys: KeyItem[]
  cursor: number
  count: number
}

export async function getInfo(siteId: string, id: string, db = 0): Promise<RedisInfo> {
  return api.get(`/sites/${siteId}/redis/${id}/info?db=${db}`)
}

/** SCAN cursor 翻页语义（Load More，PRD §11.3） */
export async function listKeys(
  siteId: string,
  id: string,
  params: { db: number; pattern: string; cursor: number; count?: number; type?: string },
): Promise<KeysPage> {
  const q = new URLSearchParams({
    db: String(params.db),
    pattern: params.pattern || '*',
    cursor: String(params.cursor),
    count: String(params.count ?? 100),
  })
  if (params.type) q.set('type', params.type)
  return api.get(`/sites/${siteId}/redis/${id}/keys?${q.toString()}`)
}

export async function getKey(siteId: string, id: string, db: number, key: string): Promise<KeyDetail> {
  return api.get(`/sites/${siteId}/redis/${id}/key?db=${db}&key=${encodeURIComponent(key)}`)
}

export function operate(
  siteId: string,
  id: string,
  body: {
    op: 'set' | 'delete' | 'expire'
    db: number
    key: string
    type?: string
    value?: unknown
    ttl?: number
  },
): Promise<{ success: boolean; latency_ms: number }> {
  return api.post(`/sites/${siteId}/redis/${id}/operations`, body)
}
