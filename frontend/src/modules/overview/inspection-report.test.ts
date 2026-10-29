import { describe, expect, it } from 'vitest'
import { buildInspectionReport, type InspectionReportInput } from './inspection-report'

const base: InspectionReportInput = {
  siteName: 'PES',
  overall: 'WARNING',
  summary: {
    server: { total: 2, healthy: 1, warning: 1, critical: 0, unknown: 0 },
    redis: { total: 1, healthy: 1, warning: 0, critical: 0, unknown: 0 },
    mq: { total: 1, healthy: 1, warning: 0, critical: 0, unknown: 0 },
    device: { total: 3, healthy: 3, warning: 0, critical: 0, unknown: 0 },
  },
  issues: [
    { kind: 'server', id: 's1', name: 'PES-21', status: 'WARNING', message: 'cpu 12%, mem 82%', checked_at: '' },
  ],
  recentOps: [
    {
      time: '2026-10-29T12:03:00+00:00',
      site: 'PES',
      resource: 'server/PES-21',
      operation: 'RESOURCE_CONFIG_UPDATED',
      target: null,
      result: 'SUCCESS',
      caller: 'Leon.Zhao',
    },
  ],
  now: new Date(2026, 9, 29, 20, 15, 3),
}

describe('buildInspectionReport', () => {
  it('有问题的站点：状态与问题行', () => {
    const text = buildInspectionReport(base)
    expect(text).toContain('整体状态：WARNING（1 个问题）')
    expect(text).toContain('  [WARNING] Server/PES-21 cpu 12%, mem 82%')
  })

  it('无问题：「待处理问题」显示「无」', () => {
    const text = buildInspectionReport({ ...base, overall: 'HEALTHY', issues: [] })
    expect(text).toContain('■ 待处理问题\n  无')
    expect(text).toContain('整体状态：HEALTHY（0 个问题）')
  })

  it('无变更：「最近变更」显示「无」', () => {
    const text = buildInspectionReport({ ...base, recentOps: [] })
    expect(text).toContain('■ 最近变更（0 条）\n  无')
  })

  it('生成时间为本地 YYYY-MM-DD HH:mm:ss', () => {
    const text = buildInspectionReport(base)
    expect(text).toMatch(/生成时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
    expect(text).toContain('生成时间：2026-10-29 20:15:03')
  })

  it('资源类型顺序固定 Server / Redis / ActiveMQ / Device', () => {
    const text = buildInspectionReport(base)
    const order = ['Server', 'Redis', 'ActiveMQ', 'Device'].map((k) => text.indexOf(`  ${k}`))
    expect(order.every((i) => i > 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
  })
})
