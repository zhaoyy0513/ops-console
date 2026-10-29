import api from '../../api'

export interface RedisInfo {
  status: string
  version: string | null
  /** master / slave */
  role: string | null
  uptime_seconds: number | null
  memory_used: number | null
  memory_peak: number | null
  /** maxmemory；0 = 未设上限 */
  memory_max: number | null
  memory_fragmentation: number | null
  connected_clients: number | null
  blocked_clients: number | null
  rejected_connections: number | null
  commands_per_sec: number | null
  /** INFO instantaneous_ops_per_sec */
  ops_per_sec: number | null
  total_commands_processed: number | null
  keyspace_hits: number | null
  keyspace_misses: number | null
  hit_rate: number | null
  evicted_keys: number | null
  expired_keys: number | null
  /** "ok" / "err"；缺失（如未开 AOF）为 null */
  rdb_last_bgsave_status: string | null
  aof_last_bgrewrite_status: string | null
  /** 最近一次 fork 耗时（µs） */
  latest_fork_usec: number | null
  db_size: number | null
  /** 各 DB 的 key 数（INFO keyspace），供 DB 下拉展示 */
  db_sizes: Record<number, number | null>
}

export interface KeyItem {
  key: string
  type: string
}

export interface KeyDetail {
  key: string
  /** 'none' = key 已不存在（后端返回该载荷而非 404，供轮询做存在性判定） */
  type: 'string' | 'hash' | 'list' | 'set' | 'zset' | 'none'
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
    /** set：value 为纯文本时目标数据结构（后端按行解析；缺省走 type 的结构化值语义） */
    struct?: 'string' | 'list' | 'set' | 'hash' | 'zset'
  },
): Promise<{ success: boolean; latency_ms: number }> {
  return api.post(`/sites/${siteId}/redis/${id}/operations`, body)
}
