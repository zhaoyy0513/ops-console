<script setup lang="ts">
/** 指标说明问号：悬停显示解释文案。用于 CardTitle 等没有 tip prop 的位置，
 *  样式与 MetricCard 内置问号一致。 */
import { TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import { HelpCircle } from 'lucide-vue-next'
import TooltipContent from '@/components/ui/tooltip/TooltipContent.vue'

defineProps<{ text: string }>()
</script>

<template>
  <TooltipProvider :delay-duration="100">
    <TooltipRoot>
      <TooltipTrigger as-child>
        <button type="button" class="tip-icon" aria-label="info">
          <HelpCircle />
        </button>
      </TooltipTrigger>
      <TooltipContent class="max-w-80 whitespace-pre-line">
        <span class="text-xs">{{ text }}</span>
      </TooltipContent>
    </TooltipRoot>
  </TooltipProvider>
</template>

<style scoped>
.tip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex: none;
  border: none;
  background: transparent;
  color: var(--ops-text-3);
  cursor: help;
  padding: 0;
  transition: color 120ms ease;
}
.tip-icon:hover {
  color: var(--ops-primary);
}
.tip-icon :deep(svg) {
  width: 14px;
  height: 14px;
}
</style>
