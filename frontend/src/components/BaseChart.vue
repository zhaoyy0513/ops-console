<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  option: Record<string, unknown>
  height?: string
}>()

const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function render() {
  chart?.setOption(props.option, true)
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(el.value!)
  render()
  window.addEventListener('resize', resize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(() => props.option, render, { deep: true })
</script>

<template>
  <div ref="el" :style="{ height: height ?? '240px', width: '100%' }" />
</template>
