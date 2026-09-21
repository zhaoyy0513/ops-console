import api from '../../api'

export interface RobotRow {
  id: string | null
  name: string | null
  status: string | null
  battery: number | string | null
  station: string | null
  task: string | null
  error: string | null
  last_update: string | null
  instance?: string
}

export const robotApi = {
  list: (siteId: string) => api.get<RobotRow[]>(`/sites/${siteId}/robots`),
  detail: (siteId: string, robotId: string, instance?: string) =>
    api.get<RobotRow>(
      `/sites/${siteId}/robots/${encodeURIComponent(robotId)}${instance ? `?instance=${instance}` : ''}`,
    ),
}
