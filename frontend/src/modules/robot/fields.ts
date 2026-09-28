/**
 * Robot 展示字段定义 —— 唯一来源（single source of truth）。
 *
 * Robot 页表头、字段映射弹窗的业务字段列都由此驱动：
 * 后续增删列只需改这个数组（后端 normalize_robot 需同步产出对应 key）。
 * 展示文案在 i18n `robot.fields.<key>`（zh/en），label 为英文兜底参考。
 */
export interface RobotFieldDef {
  /** 平台内部字段 key（RobotRow 的属性名），同时是 i18n key（robot.fields.<key>） */
  key: string
  /** 英文展示名（兜底参考；界面文案请用 $t(`robot.fields.${key}`)） */
  label: string
}

export const ROBOT_FIELDS: RobotFieldDef[] = [
  { key: 'id', label: 'RobotCode' },
  { key: 'name', label: 'RobotName' },
  { key: 'status', label: 'Status' },
  { key: 'battery', label: 'Battery' },
  { key: 'station', label: 'Position' },
  { key: 'lift', label: 'Lift' },
  { key: 'shelf_code', label: 'ShelfCode' },
]
