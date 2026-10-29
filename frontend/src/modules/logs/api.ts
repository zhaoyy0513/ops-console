import api from '../../api'

/** 日志源（站点级白名单）：只存 label + 远端绝对路径。 */
export interface LogSource {
  id: string
  label: string
  path: string
}

/** 一次字节窗口读取的结果。start_offset = 内容首字节，next_offset = 末字节之后。 */
export interface LogReadResult {
  content: string
  start_offset: number
  next_offset: number
  size: number
  inode: string
  eof: boolean
  truncated: boolean
  error?: string | null
  error_code?: string | null
}

export type LogMode = 'tail' | 'head' | 'offset' | 'search'

/** 日志源目录下的一个文件（只含元数据，不含内容） */
export interface LogFile {
  name: string
  size: number
  mtime: number
}

export interface LogFileList {
  files: LogFile[]
  truncated: boolean
  error?: string | null
  error_code?: string | null
}

export const logsApi = {
  list: (siteId: string) => api.get<LogSource[]>(`/logs/${siteId}`),
  create: (siteId: string, data: { label: string; path: string }) =>
    api.post<LogSource>(`/logs/${siteId}`, data),
  update: (siteId: string, id: string, data: Partial<Pick<LogSource, 'label' | 'path'>>) =>
    api.put<LogSource>(`/logs/${siteId}/${id}`, data),
  remove: (siteId: string, id: string) => api.delete<void>(`/logs/${siteId}/${id}`),
  /** 列出日志源目录下的文件（只 stat，不读内容） */
  listFiles: (siteId: string, id: string) =>
    api.get<LogFileList>(`/logs/${siteId}/${id}/files`, { timeout: 20_000 }),
  read: (
    siteId: string,
    id: string,
    params: { file: string; mode: LogMode; offset?: number; kw?: string; lines?: number },
  ) => {
    const qs = new URLSearchParams({ mode: params.mode, file: params.file })
    if (params.offset != null) qs.set('offset', String(params.offset))
    if (params.kw) qs.set('kw', params.kw)
    if (params.lines != null) qs.set('lines', String(params.lines))
    // 读取要建 SSH 连接，比默认 15s 稍宽
    return api.get<LogReadResult>(`/logs/${siteId}/${id}/read?${qs}`, { timeout: 20_000 })
  },
}
