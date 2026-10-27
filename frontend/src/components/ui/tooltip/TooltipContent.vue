<script setup lang="ts">
import { TooltipContent as RContent, TooltipPortal } from 'reka-ui'
import { cn } from '@/lib/utils'

// 深色 tooltip（用户决策 2026-10-26）：黑白对比在明暗两套主题下都成立，
// 且比白底更"工具感"。外部 class 与基础类合并而非替换（曾有透明 bug）。
const props = withDefaults(defineProps<{ class?: string; sideOffset?: number }>(), {
  sideOffset: 6,
})
</script>

<template>
  <TooltipPortal>
    <RContent
      side="top"
      :side-offset="props.sideOffset"
      :class="
        cn(
          'z-[60] max-w-xs rounded-md border border-black/20 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-50 shadow-lg dark:border-white/15 dark:bg-neutral-950',
          props.class,
        )
      "
    >
      <slot />
    </RContent>
  </TooltipPortal>
</template>
