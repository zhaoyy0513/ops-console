import type { OverviewData } from './api'

/** 纯文本巡检报告（贴群/贴客户用）：输入 Overview 页已有数据，不发起任何请求。 */
export interface InspectionReportInput {
  siteName: string
  overall: OverviewData['overall']
  summary: OverviewData['summary']
  issues: OverviewData['issues']
  /** 新→旧，最多取前 5 条 */
  recentOps: OverviewData['recent_ops']
  /** 生成时间；测试注入固定值 */
  now?: Date
}

const KIND_ORDER = ['server', 'redis', 'mq', 'device'] as const
const KIND_LABEL: Record<string, string> = { server: 'Server', redis: 'Redis', mq: 'ActiveMQ', device: 'Device' }
const KIND_UNIT: Record<string, string> = { server: '台', redis: '个', mq: '个', device: '个' }

/** oplog 操作码 → 人话（未命中时原样输出） */
const OP_LABEL: Record<string, string> = {
  RESOURCE_CONFIG_CREATED: '新增 资源',
  RESOURCE_CONFIG_UPDATED: '修改 资源',
  RESOURCE_CONFIG_DELETED: '删除 资源',
  SITE_CREATED: '新增 站点',
  SITE_UPDATED: '修改 站点',
  SITE_DELETED: '删除 站点',
  IMPORT_CONFIG: '导入 配置',
  SSH_SCRIPT_RUN: '执行 脚本',
  MQ_EMPTY_QUEUE: '清空 队列',
  REDIS_SET_KEY: '写入 Redis',
  REDIS_DELETE_KEY: '删除 Redis',
  REDIS_EXPIRE_KEY: '设置 Redis TTL',
  KNOWLEDGE_CREATED: '新增 知识',
  KNOWLEDGE_UPDATED: '修改 知识',
  KNOWLEDGE_DELETED: '删除 知识',
}

const pad = (n: number) => String(n).padStart(2, '0')

export function buildInspectionReport(input: InspectionReportInput): string {
  const now = input.now ?? new Date()
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  const clock = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`

  const lines: string[] = [
    `【站点巡检报告】${input.siteName}`,
    `生成时间：${date} ${clock}`,
    `整体状态：${input.overall}（${input.issues.length} 个问题）`,
    '',
    '■ 资源概况',
  ]

  for (const kind of KIND_ORDER) {
    const s = input.summary[kind]
    const dist =
      [
        s.healthy ? `健康 ${s.healthy}` : '',
        s.warning ? `警告 ${s.warning}` : '',
        s.critical ? `严重 ${s.critical}` : '',
        s.unknown ? `未知 ${s.unknown}` : '',
      ]
        .filter(Boolean)
        .join(' / ') || '无'
    lines.push(`  ${KIND_LABEL[kind].padEnd(11)}${s.total} ${KIND_UNIT[kind]}   ${dist}`)
  }

  lines.push('', '■ 待处理问题')
  if (input.issues.length) {
    for (const i of input.issues) {
      lines.push(`  [${i.status}] ${KIND_LABEL[i.kind] ?? i.kind}/${i.name} ${i.message}`)
    }
  } else {
    lines.push('  无')
  }

  const ops = input.recentOps.slice(0, 5)
  lines.push('', `■ 最近变更（${ops.length} 条）`)
  if (ops.length) {
    for (const op of ops) {
      const d = new Date(op.time)
      const hm = Number.isNaN(d.getTime())
        ? op.time.slice(11, 16)
        : `${pad(d.getHours())}:${pad(d.getMinutes())}`
      const who = op.caller && op.caller !== '-' ? op.caller : '匿名'
      lines.push(`  ${hm}  ${who}  ${OP_LABEL[op.operation] ?? op.operation} ${op.resource}`)
    }
  } else {
    lines.push('  无')
  }

  lines.push('', '—— 由 Ops Console 生成')
  return lines.join('\n')
}
