/** 磁盘写满预测：页面内采样 + 最小二乘线性外推（纯函数，便于单测）。
 *
 * 后端只采样 cpu/mem，没有磁盘序列；ServerView 在页面在场期间把每次轮询的
 * use_percent 追加到内存（≤40 点），这里只负责「点 → 天数」。
 */

export interface DiskSample {
  /** 毫秒时间戳 */
  t: number
  /** 使用率 % */
  v: number
}

const MAX_POINTS = 40

/**
 * 用最近样本做最小二乘，推算「写满剩余天数」。
 *
 * 返回 null 的情况（前端显示 '-'）：样本不足 minPoints、时间戳无跨度、
 * 斜率 ≤0（未增长/在下降）、已满（≥100%，无剩余可算）。
 */
export function forecastDays(samples: DiskSample[], current: number, minPoints = 10): number | null {
  const pts = samples.slice(-MAX_POINTS)
  const remain = 100 - current
  if (pts.length < minPoints || remain <= 0) return null

  const n = pts.length
  const t0 = pts[0].t
  // 时间单位取小时：3s 间隔直接用毫秒会让斜率落到浮点噪声量级
  const xs = pts.map((p) => (p.t - t0) / 3_600_000)
  const ys = pts.map((p) => p.v)
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  let num = 0
  let den = 0
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my)
    den += (xs[i] - mx) ** 2
  }
  if (den <= 0) return null // 同一时刻的重复点，斜率无定义
  const perHour = num / den
  if (!(perHour > 0)) return null
  return remain / (perHour * 24)
}
