<script setup lang="ts">
/** 通用指标卡（ui-upgrade-design.md §6.1）：图标 + 标题 + CountUp 数值 +
 *  slot（副文案/迷你图）。
 *  顶边 2px 状态色条为 opt-in：仅传 barColor 时渲染，否则完全素卡。
 *  聚光效果（Phase D §5.2④）同为 opt-in：仅 hoverable（可点击）卡片跟随
 *  鼠标更新 --sx/--sy，极淡一层光斑；非交互卡完全素面。 */
import type { Component } from 'vue'
import { TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import { HelpCircle } from 'lucide-vue-next'
import TooltipContent from '@/components/ui/tooltip/TooltipContent.vue'
import CountUp from './bits/CountUp.vue'

const props = withDefaults(
  defineProps<{
    title: string
    icon?: Component
    /** 数值；null/undefined 显示 ? */
    value?: number | null
    decimals?: number
    prefix?: string
    suffix?: string
    /** 数值颜色（如 pctColor() 结果） */
    color?: string
    /** 顶边 2px 状态色条，opt-in：不传则不渲染色条（素卡） */
    barColor?: string
    /** hover 边框高亮改为 opt-in：仅可点击卡片传 true，非交互卡不暗示可点 */
    hoverable?: boolean
    /** 指标说明：标题右侧出现问号，悬停解释「这个数字是什么、怎么看」 */
    tip?: string
  }>(),
  { value: null, decimals: 0, prefix: '', suffix: '', hoverable: false },
)

/** 跟随鼠标更新聚光位置：只写 CSS 变量，不进响应式状态、不触发重渲 */
function onSpotMove(e: MouseEvent) {
  if (!props.hoverable) return
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--sx', `${e.clientX - r.left}px`)
  el.style.setProperty('--sy', `${e.clientY - r.top}px`)
}
</script>

<template>
  <div class="metric-card" :class="{ hoverable }" @mousemove="onSpotMove">
    <div v-if="barColor" class="mc-bar" :style="{ background: barColor }" />
    <div v-if="hoverable" class="mc-spot" aria-hidden="true" />
    <div class="mc-head">
      <span v-if="icon" class="mc-icon inline-flex size-[14px] shrink-0 [&_svg]:size-full">
        <component :is="icon" />
      </span>
      <span class="mc-title">{{ title }}</span>
      <TooltipProvider v-if="tip" :delay-duration="100">
        <TooltipRoot>
          <TooltipTrigger as-child>
            <button type="button" class="mc-tip-btn" :aria-label="title">
              <HelpCircle />
            </button>
          </TooltipTrigger>
          <TooltipContent class="max-w-80 whitespace-pre-line">
            <span class="text-xs">{{ tip }}</span>
          </TooltipContent>
        </TooltipRoot>
      </TooltipProvider>
    </div>
    <!-- 无 value 且 slot 承载内容（如 donut/网络双行）时不渲染数值行，避免出现孤立的 "?" -->
    <div v-if="value != null || !$slots.default" class="mc-value" :style="color ? { color } : undefined">
      <CountUp v-if="value != null" :value="value" :decimals="decimals" :prefix="prefix" :suffix="suffix" />
      <span v-else>?</span>
    </div>
    <div v-if="$slots.default" class="mc-extra"><slot /></div>
  </div>
</template>

<style scoped>
.metric-card {
  position: relative;
  background: var(--ops-surface);
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m, 8px);
  padding: 12px 14px;
  overflow: hidden;
  transition: border-color 160ms ease;
}
.metric-card.hoverable:hover {
  border-color: var(--ops-primary);
}
/* 聚光层（§5.2④）：全项目唯一光效，240px 大半径 + 8% 极低透明度 */
.mc-spot {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    240px circle at var(--sx, 50%) var(--sy, 50%),
    rgba(37, 99, 235, 0.08),
    transparent 65%
  );
  opacity: 0;
  transition: opacity 160ms ease;
  pointer-events: none;
}
.metric-card.hoverable:hover .mc-spot {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .mc-spot {
    display: none; /* 光斑淡入属动效，reduced-motion 下整体关闭 */
  }
}
.mc-tip-btn {
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
.mc-tip-btn:hover { color: var(--ops-primary); }
.mc-tip-btn :deep(svg) { width: 14px; height: 14px; }
.mc-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
}
.mc-head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ops-text-2);
  font-size: 12px;
}
.mc-icon {
  color: var(--ops-text-3);
}
.mc-value {
  margin-top: 6px;
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--ops-text-1);
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
.mc-extra {
  margin-top: 6px;
  color: var(--ops-text-3);
  font-size: 12px;
  line-height: 1.5;
}
</style>
