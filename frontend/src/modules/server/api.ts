import api from '../../api'

export interface DiskRow {
  mount: string
  size: string
  used: string
  avail: string
  use_percent: number
  inode_percent?: number
}

export interface Issue {
  type: string
  severity: 'WARNING' | 'CRITICAL'
  value: number
  threshold: number
  message: string
  /** 仅 DISK_HIGH：挂载点 */
  mount?: string
}

export interface ServerMetrics {
  cpu: { usage: number | null; iowait: number | null; cores: number | null }
  load: { load1: number | null; load5: number | null; load15: number | null }
  memory: {
    total: number | null
    used: number | null
    available: number | null
    cached: number | null
    swap_total: number | null
    swap_used: number | null
  }
  network: { rx: number; tx: number; errors: number; dropped: number }
  disk: DiskRow[]
  diagnosis: { status: string; issues: Issue[] }
}

export interface ProcessRow {
  pid: number
  cpu_percent: number
  mem_percent: number
  command: string
}

export const serverApi = {
  metrics: (siteId: string, serverId: string) =>
    api.get<ServerMetrics>(`/sites/${siteId}/servers/${serverId}/metrics`),
  processes: (siteId: string, serverId: string) =>
    api.get<ProcessRow[]>(`/sites/${siteId}/servers/${serverId}/processes`),
}
