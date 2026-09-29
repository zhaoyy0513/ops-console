/** ECharts 按需引入 + ops 主题注册（ui-upgrade-design.md §3.4）。
 *  - 只注册实际用到的 chart/组件，替代全量 `import * as echarts`；
 *  - ops-light / ops-dark 双主题，色板与 styles/tokens.css 同源；
 *  - BaseChart 统一从这里 init，业务代码不得直连 echarts。 */
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, PieChart,
  GridComponent, LegendComponent, TitleComponent, TooltipComponent,
  CanvasRenderer,
])

const MONO = "'JetBrains Mono Variable', ui-monospace, Consolas, monospace"

function mkTheme(dark: boolean) {
  const axisBase = {
    axisLine: { lineStyle: { color: dark ? '#2e2e35' : '#e5e6eb' } },
    axisLabel: { color: dark ? '#a9a9b3' : '#86909c' },
    axisTick: { lineStyle: { color: dark ? '#2e2e35' : '#e5e6eb' } },
    splitLine: { lineStyle: { color: dark ? '#26262c' : '#f2f3f5' } },
  }
  return {
    // 与 tokens 同源：primary 蓝 + 语义色；暗色提亮一档
    color: dark
      ? ['#3b82f6', '#f5a623', '#27ae60', '#9d7cff', '#e05270']
      : ['#2563eb', '#f0a020', '#18a058', '#722ed1', '#d03050'],
    backgroundColor: 'transparent',
    textStyle: { color: dark ? '#a9a9b3' : '#4e5969', fontFamily: MONO },
    categoryAxis: axisBase,
    valueAxis: axisBase,
  }
}

echarts.registerTheme('ops-light', mkTheme(false))
echarts.registerTheme('ops-dark', mkTheme(true))

export default echarts
export type EChartsType = echarts.ECharts
