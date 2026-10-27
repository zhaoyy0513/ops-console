import api from '../../api'

export interface SshScript {
  id: string
  name: string
  server_id: string
  content: string
  enabled: boolean
  /** 非空 = 定时脚本（标准 5 段 cronie 格式） */
  cron?: string | null
  /** 定时开关（仅定时脚本有意义） */
  sched_enabled?: boolean
  server_name?: string
}

export const sshApi = {
  list: (siteId: string) => api.get<SshScript[]>(`/sites/${siteId}/ssh_scripts`),
  create: (siteId: string, data: Partial<SshScript>) =>
    api.post<SshScript>(`/sites/${siteId}/ssh_scripts`, data),
  update: (siteId: string, id: string, data: Partial<SshScript>) =>
    api.put<SshScript>(`/sites/${siteId}/ssh_scripts/${id}`, data),
  remove: (siteId: string, id: string) =>
    api.delete<void>(`/sites/${siteId}/ssh_scripts/${id}`),
  run: (siteId: string, id: string) =>
    api.post<{ stdout: string; stderr: string; timed_out: boolean; latency_ms: number }>(
      `/sites/${siteId}/ssh_scripts/${id}/run`, undefined, { timeout: 90_000 },
    ),
  /** 编辑弹窗测试：直接执行表单内容（不落库） */
  runAdhoc: (siteId: string, serverId: string, content: string) =>
    api.post<{ stdout: string; stderr: string; timed_out: boolean; latency_ms: number }>(
      `/sites/${siteId}/ssh_scripts/run-adhoc`, { server_id: serverId, content },
      { timeout: 90_000 }),

  /** 流式执行（SSE）：onChunk(kind,data) 实时回调；返回 abort 用于关闭窗口时终止远端进程 */
  /** 风险预检（run/save 前调用渲染确认框；执行时后端仍兜底校验） */
  assessRisk: (content: string) =>
    api.post<{ level: 'safe' | 'warn' | 'block'; patterns: string[] }>('/ssh/assess-risk', { content }),
  runStream: (siteId: string, id: string, onChunk: (kind: string, data: string) => void, confirmRisk = false) =>
    streamFetch(`/sites/${siteId}/ssh_scripts/${id}/run-stream?confirm_risk=${confirmRisk}`, undefined, onChunk),
  runAdhocStream: (
    siteId: string, serverId: string, content: string,
    onChunk: (kind: string, data: string) => void,
    confirmRisk = false,
  ) =>
    streamFetch(`/sites/${siteId}/ssh_scripts/run-adhoc-stream`,
      { server_id: serverId, content, confirm_risk: confirmRisk }, onChunk),
}

function streamFetch(
  path: string, body: unknown | undefined, onChunk: (kind: string, data: string) => void,
): () => void {
  const ctrl = new AbortController()
  const abort = () => ctrl.abort()
  ;(async () => {
    try {
      const resp = await fetch('/api' + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!resp.ok || !resp.body) {
        onChunk('error', `HTTP ${resp.status}`)
        return
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(line.slice(6))
            onChunk(ev.kind, ev.data)
          } catch { /* 半包忽略，下轮补齐 */ }
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') onChunk('error', (e as Error).message)
    }
  })()
  return abort
}