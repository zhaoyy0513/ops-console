<script setup lang="ts">
/** 统一点状加载动画（替代裸 spinner）：三点依次起伏 + 可选文案。
    width 控制点大小，用于表格/小区域（sm）与整页（md）。 */
withDefaults(defineProps<{ text?: string; size?: 'sm' | 'md' }>(), { size: 'md' })
</script>

<template>
  <div class="inline-flex items-center justify-center gap-2.5" role="status" aria-live="polite">
    <span class="dots" :class="size === 'sm' ? 'dots-sm' : 'dots-md'">
      <i /><i /><i />
    </span>
    <span v-if="text" class="text-xs text-muted-foreground">{{ text }}</span>
  </div>
</template>

<style scoped>
.dots {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dots i {
  display: block;
  border-radius: 9999px;
  background: var(--primary);
  animation: dot-bounce 1.2s ease-in-out infinite;
}
.dots-md i {
  width: 6px;
  height: 6px;
}
.dots-sm i {
  width: 4px;
  height: 4px;
}
.dots i:nth-child(2) {
  animation-delay: 0.15s;
  opacity: 0.75;
}
.dots i:nth-child(3) {
  animation-delay: 0.3s;
  opacity: 0.5;
}
@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-5px); }
}
@media (prefers-reduced-motion: reduce) {
  .dots i { animation: none; }
}
</style>
