<script setup lang="ts">
import { ProgressRoot, ProgressIndicator } from 'reka-ui'
import { cn } from '@/lib/utils'

const props = defineProps<{
  /** 0~100 */
  value?: number | null
  /** 超过该值变 critical 色（如 90）；默认无 */
  dangerAt?: number
  class?: string
}>()

const color = (v: number) =>
  props.dangerAt != null && v >= props.dangerAt ? 'bg-[var(--ops-critical)]' : 'bg-primary'
</script>

<template>
  <ProgressRoot
    :value="value ?? 0"
    class="relative h-1.5 w-full overflow-hidden rounded-full bg-secondary"
  >
    <ProgressIndicator
      v-if="value != null"
      :class="cn('h-full transition-all', color(value))"
      :style="{ width: `${Math.min(100, Math.max(0, value))}%` }"
    />
  </ProgressRoot>
</template>
