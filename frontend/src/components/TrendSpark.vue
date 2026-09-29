<script setup lang="ts">
/** 迷你趋势线（ui-upgrade-design.md §6.1 TrendSpark）：
 *  纯 SVG polyline，无坐标轴无交互；比每行一个 echarts 实例轻得多
 *  （MQ 队列表每行一列的场景）。 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    data: number[]
    width?: number
    height?: number
    color?: string
  }>(),
  { width: 84, height: 22, color: '#2563eb' },
)

const points = computed(() => {
  const d = props.data
  if (d.length < 2) return ''
  const max = Math.max(...d)
  const min = Math.min(...d)
  const range = max - min || 1
  const sx = (i: number) => (i / (d.length - 1)) * (props.width - 2) + 1
  const sy = (v: number) => props.height - 2 - ((v - min) / range) * (props.height - 4)
  return d.map((v, i) => `${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join(' ')
})
</script>

<template>
  <svg :width="width" :height="height" class="trend-spark" aria-hidden="true">
    <polyline :points="points" fill="none" :stroke="color" stroke-width="1.5" stroke-linejoin="round" />
  </svg>
</template>

<style scoped>
.trend-spark {
  display: block;
}
</style>
