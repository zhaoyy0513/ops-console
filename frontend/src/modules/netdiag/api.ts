import api from '../../api'

/** 依赖连通性矩阵的一行：一个已配置资源的 TCP 探测结果。 */
export interface NetdiagRow {
  resource_type: 'servers' | 'redis' | 'mq' | 'devices'
  resource_name: string
  host: string
  port: number | null
  ok: boolean
  latency_ms: number
  error: string | null
}

export const netdiagApi = {
  /** 后端出站探测；目标多时按 10 并发 × 3s 超时排队，放宽 axios 超时避免前端先断 */
  matrix: (siteId: string) =>
    api.get<NetdiagRow[]>(`/netdiag/${siteId}/matrix`, { timeout: 60000 }),
}
