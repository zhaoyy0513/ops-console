import { describe, expect, it } from 'vitest'
import { forecastDays, type DiskSample } from './forecast'

/** 每分钟一个点，共 count 个 */
function series(count: number, startPct: number, perMinute: number): DiskSample[] {
  const t0 = Date.UTC(2026, 9, 29, 10, 0, 0)
  return Array.from({ length: count }, (_, i) => ({ t: t0 + i * 60_000, v: startPct + perMinute * i }))
}

describe('forecastDays', () => {
  it('样本不足 10 点 -> null', () => {
    expect(forecastDays(series(9, 50, 0.1), 50.8)).toBeNull()
  })

  it('使用率不变 -> null（斜率 0）', () => {
    expect(forecastDays(series(20, 60, 0), 60)).toBeNull()
  })

  it('使用率下降 -> null（斜率 ≤0，不预测）', () => {
    expect(forecastDays(series(20, 60, -0.2), 56.2)).toBeNull()
  })

  it('已满（≥100%）-> null，不给出 0 天', () => {
    expect(forecastDays(series(20, 90, 1), 100)).toBeNull()
  })

  it('时间戳无跨度 -> null', () => {
    const t = Date.UTC(2026, 9, 29, 10, 0, 0)
    const pts = Array.from({ length: 12 }, () => ({ t, v: 50 }))
    expect(forecastDays(pts, 50)).toBeNull()
  })

  it('每分钟 +0.1%（=144 点/天）：从 52% 到满约 0.333 天', () => {
    const pts = series(21, 50, 0.1) // 50.0 .. 52.0
    const days = forecastDays(pts, 52)
    expect(days).not.toBeNull()
    expect(days!).toBeCloseTo(48 / 144, 6)
  })

  it('噪声下的上升趋势仍给出合理量级（每分钟 +0.05% -> 约 0.69 天）', () => {
    const pts = series(21, 50, 0.05).map((p, i) => ({ ...p, v: p.v + (i % 2 ? 0.01 : -0.01) }))
    const days = forecastDays(pts, pts[pts.length - 1].v)
    expect(days).not.toBeNull()
    expect(days!).toBeGreaterThan(0.5)
    expect(days!).toBeLessThan(1.5)
  })
})
