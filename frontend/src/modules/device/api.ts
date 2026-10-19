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

export const deviceApi = {
  /** instance 指定单实例（页面下拉选择）；缺省聚合全部启用实例。
   *  上游设备接口响应慢，表格/详情给 30s 超时（全局默认 10s 不够） */
  list: (siteId: string, instance?: string) =>
    api.get<DeviceRow[]>(`/sites/${siteId}/devices${instance ? `?instance=${encodeURIComponent(instance)}` : ''}`, { timeout: 30_000 }),
  detail: (siteId: string, deviceId: string, instance?: string) =>
    api.get<DeviceRow>(
      `/sites/${siteId}/devices/${encodeURIComponent(deviceId)}${instance ? `?instance=${instance}` : ''}`,
      { timeout: 30_000 },
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
