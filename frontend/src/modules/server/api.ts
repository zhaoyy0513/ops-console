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

/** 失败 systemd 单元（systemctl --failed） */
export interface FailedUnit {
  unit: string
  description: string
}

/** OOM 击杀记录（内核日志；time 尽力而为，解析不到为 null） */
export interface OomEvent {
  time: string | null
  process: string | null
  detail: string
}

/** 同一次采集内的能力探测：false = 该项不可用，前端显示「不可用」而不是 0 */
export interface ServerCapabilities {
  root: boolean
  psi: boolean
  dmesg: boolean
  systemctl: boolean
  kernlog: boolean
  syslog: boolean
}

export interface ServerMetrics {
  cpu: { usage: number | null; iowait: number | null; steal?: number | null; cores: number | null }
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
  /** 磁盘 IO 累计计数（/proc/diskstats 全盘聚合，扇区×512B）；受限环境为 null */
  disk_io?: {
    read_bytes: number
    write_bytes: number
    read_iops: number
    write_iops: number
  } | null
  disk: DiskRow[]
  diagnosis: { status: string; issues: Issue[] }
  /** 僵尸进程数（metrics 同一 SSH 会话采集；后端未提供时为 undefined） */
  zombie_count?: number | null
  /** uptime 的 `up ...` 片段（如 "37 days, 4:21"） */
  uptime_text?: string | null
  /** 启动时间（ISO，无时区）；容器内 who -b 为空时为 null */
  boot_time?: string | null
  /** 文件句柄使用率（/proc/sys/fs/file-nr）；解析失败为 null */
  fd_usage?: { allocated: number; max: number; percent: number } | null
  /** 失败的 systemd 单元；不可用为 null（原因见 failed_units_unavailable） */
  failed_units?: FailedUnit[] | null
  failed_units_unavailable?: string | null
  /** 最近 OOM 击杀记录；三路日志源都不可读为 null */
  oom_events?: OomEvent[] | null
  oom_unavailable?: string | null
  capabilities?: ServerCapabilities | null
}

export interface ProcessRow {
  pid: number
  cpu_percent: number
  mem_percent: number
  command: string
}

export interface ZombieGroup {
  /** 父进程 PID（僵尸自身 cmdline 为空，有用信息是未收尸的父进程，故按父进程分组） */
  ppid: number
  count: number
  cmd: string
}

export const serverApi = {
  metrics: (siteId: string, serverId: string) =>
    api.get<ServerMetrics>(`/sites/${siteId}/servers/${serverId}/metrics`),
  processes: (siteId: string, serverId: string) =>
    api.get<ProcessRow[]>(`/sites/${siteId}/servers/${serverId}/processes`),
  zombies: (siteId: string, serverId: string) =>
    api.get<{ total: number; groups: ZombieGroup[] }>(`/sites/${siteId}/servers/${serverId}/zombies`),
  killZombie: (siteId: string, serverId: string, pid: number, comm?: string) =>
    // comm 仅作 oplog 展示用，走 query 参数
    api.post<{ killed: boolean }>(
      `/sites/${siteId}/servers/${serverId}/zombies/${pid}/kill` +
        (comm ? `?comm=${encodeURIComponent(comm)}` : ''),
    ),
}
