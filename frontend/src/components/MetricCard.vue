<script setup lang="ts">
/** 通用指标卡（ui-upgrade-design.md §6.1）：图标 + 标题 + CountUp 数值 +
 *  顶边 2px 状态色条 + slot（副文案/迷你图）。
 *  容器为 SpotlightCard 的降级形态（普通卡 + hover 边框高亮），
 *  光效版本待 Phase D 评审后决定是否启用。 */
import type { Component } from 'vue'
import { NIcon } from 'naive-ui'
import CountUp from './bits/CountUp.vue'

withDefaults(
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
    /** 顶边状态色条，默认主色 */
    barColor?: string
  }>(),
  { value: null, decimals: 0, prefix: '', suffix: '' },
)
</script>

<template>
  <div class="metric-card">
    <div class="mc-bar" :style="{ background: barColor ?? 'var(--ops-primary)' }" />
    <div class="mc-head">
      <n-icon v-if="icon" :component="icon" :size="14" class="mc-icon" />
      <span class="mc-title">{{ title }}</span>
    </div>
    <div class="mc-value" :style="color ? { color } : undefined">
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
.metric-card:hover {
  border-color: var(--ops-primary);
}
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
