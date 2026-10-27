<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<!-- 带 action 具名插槽：标题行右侧放按钮（CardHeader 官方 grid 规格） -->
<template>
  <div :class="cn('flex items-center justify-between gap-4 px-5 pt-4 pb-3', props.class)">
    <div class="flex flex-col gap-0.5">
      <slot />
    </div>
    <slot name="action" />
  </div>
</template>
