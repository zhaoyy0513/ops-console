import api from '../../api'

/** 自定义展示字段（与后端 DeviceCustomField 同构）；key 生成一次后稳定 */
export interface DeviceCustomField {
  key: string
  label_zh: string
  label_en: string
  bind?: string | null
  template?: string | null
  value_map?: Record<string, string> | null
}

export interface DeviceRow {
  id: string | null
  name: string | null
  status: string | null
  battery: number | string | null
  station: string | null
  error: string | null
  last_update: string | null
  instance?: string
  /** 自定义字段的取值由后端 normalize 写入各项稳定 key（cf_xxxxx）下 */
  [key: string]: unknown
}

/** 字段映射失效项：业务字段名 + 声明的上游路径 */
export interface DeviceMissingField {
  field: string
  source: string
}

/** 实例健康：最近一次响应耗时 + 映射失效（ok=false 表示上游不可达，耗时仍可能带回） */
export interface DeviceHealth {
  ok: boolean
  latency_ms: number | null
  missing_fields: DeviceMissingField[]
}

export const deviceApi = {
  /** instance 指定单实例（页面下拉选择）；缺省聚合全部启用实例（走全局 15s 超时） */
  list: (siteId: string, instance?: string) =>
    api.get<DeviceRow[]>(`/sites/${siteId}/devices${instance ? `?instance=${encodeURIComponent(instance)}` : ''}`),
  detail: (siteId: string, deviceId: string, instance?: string) =>
    api.get<DeviceRow>(
      `/sites/${siteId}/devices/${encodeURIComponent(deviceId)}${instance ? `?instance=${instance}` : ''}`,
    ),
  /** 实例健康：响应耗时 + 字段映射失效（与列表共用同一次上游拉取） */
  health: (siteId: string, deviceId: string) =>
    api.get<DeviceHealth>(
      `/sites/${siteId}/device-instances/${encodeURIComponent(deviceId)}/health`,
    ),
  /** 获取一条原始 JSON 数据及其字段名列表（字段映射配置用） */
  sampleFields: (siteId: string, deviceId: string) =>
    api.get<{ fields: string[]; sample: Record<string, unknown> }>(
      `/sites/${siteId}/device-instances/${encodeURIComponent(deviceId)}/sample-fields`,
    ),
  /** 全部站点 Device 实例的映射配置（克隆用，不分站点） */
  listMappings: () =>
    api.get<Array<{
      site_id: string
      site_name: string
      device_id: string
      device_name: string
      field_map: Record<string, string> | null
      value_map: Record<string, Record<string, string>> | null
      custom_fields?: DeviceCustomField[] | null
    }>>('/devices/mappings'),
}
