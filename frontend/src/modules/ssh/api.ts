import api from '../../api'

export interface SshScript {
  id: string
  name: string
  server_id: string
  content: string
  enabled: boolean
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
      `/sites/${siteId}/ssh_scripts/${id}/run`,
    ),
}
