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
  /** instance 指定单实例（页面下拉选择）；缺省聚合全部启用实例 */
  list: (siteId: string, instance?: string) =>
    api.get<RobotRow[]>(`/sites/${siteId}/robots${instance ? `?instance=${encodeURIComponent(instance)}` : ''}`),
  detail: (siteId: string, robotId: string, instance?: string) =>
    api.get<RobotRow>(
      `/sites/${siteId}/robots/${encodeURIComponent(robotId)}${instance ? `?instance=${instance}` : ''}`,
    ),
  /** 获取一条原始 JSON 数据及其字段名列表（字段映射配置用） */
  sampleFields: (siteId: string, robotId: string) =>
    api.get<{ fields: string[]; sample: Record<string, unknown> }>(
      `/sites/${siteId}/robot-instances/${encodeURIComponent(robotId)}/sample-fields`,
    ),
}
