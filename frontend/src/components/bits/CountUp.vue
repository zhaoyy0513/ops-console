<script setup lang="ts">
/** 数字滚动（vue-bits CountUp 的手写等价实现，rAF tween，零依赖）。
 *  L2 氛围增强：监控数值从旧值滚到新值。
 *  性能守则（§2.2）：duration 默认压到 600ms（3s 轮询不能常滚）；
 *  只在值变化时 tween，初始值直出；尊重 prefers-reduced-motion 直跳。 */
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    value: number
    /** tween 时长 ms，0 = 直跳 */
    duration?: number
    decimals?: number
    prefix?: string
    suffix?: string
  }>(),
  { duration: 600, decimals: 0, prefix: '', suffix: '' },
)

const display = ref(props.value)
let raf = 0

function fmt(v: number): string {
  return v.toLocaleString('en-US', {
    minimumFractionDigits: props.decimals,
    maximumFractionDigits: props.decimals,
  })
}

watch(
  () => props.value,
  (to, from) => {
    cancelAnimationFrame(raf)
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!props.duration || reduced) {
      display.value = to
      return
    }
    const a = from ?? to
    const start = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / props.duration)
      const eased = 1 - (1 - p) ** 3 // easeOutCubic
      display.value = a + (to - a) * eased
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  },
)

onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <span class="count-up">{{ prefix }}{{ fmt(display) }}{{ suffix }}</span>
</template>

<style scoped>
/* 等宽 + 表格数字：轮询刷新时宽度不抖（§3.3） */
.count-up {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
</style>
