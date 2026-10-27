<script setup lang="ts">
/** 图表底座：统一主题（随画风切换销毁重建）、容器级 resize 监听、
 *  loading / empty 内置态。业务图表只传 option。 */
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type ComputedRef } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import echarts from '../utils/echarts'

const props = defineProps<{
  option: Record<string, unknown>
  height?: string
  loading?: boolean
  /** 空态文案（图表容器保留高度，文案覆盖其上，布局不跳） */
  empty?: string
}>()

// 明暗二态，echarts 主题 ops-light / ops-dark（utils/echarts.ts 注册）
const theme = inject<ComputedRef<'light' | 'dark'>>('opsTheme', computed(() => 'light'))

const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function themeName() {
  return theme.value === 'light' ? 'ops-light' : 'ops-dark'
}

function render() {
  chart?.setOption(props.option, true)
}

useResizeObserver(el, () => chart?.resize())

onMounted(() => {
  chart = echarts.init(el.value!, themeName())
  render()
})

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})

watch(() => props.option, render, { deep: true })
// 主题不能热切：销毁后以新主题重建（watch 映射后的主题名，mono/terminal 同为暗不重复重建）
watch(themeName, () => {
  chart?.dispose()
  chart = echarts.init(el.value!, themeName())
  render()
})
</script>

<template>
  <div class="base-chart" :style="{ height: height ?? '240px' }">
    <div ref="el" style="width: 100%; height: 100%" />
    <div v-if="empty" class="chart-empty">{{ empty }}</div>
    <div v-if="loading" class="chart-spin">
      <span class="inline-block size-4 rounded-full border-2 border-border border-t-muted-foreground animate-spin" />
    </div>
  </div>
</template>

<style scoped>
.base-chart {
  position: relative;
}
.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ops-text-3);
  font-size: 12px;
}
.chart-spin {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
