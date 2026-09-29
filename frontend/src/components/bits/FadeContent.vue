<script setup lang="ts">
/** 淡入过渡（vue-bits FadeContent 的手写等价实现，纯 CSS）。
 *  L2 最克制进场：120~160ms 淡入 + 4px 上移，无滑入/缩放。
 *  仅首次挂载触发；轮询数据更新不经过本组件。 */
import { onMounted, ref } from 'vue'

withDefaults(defineProps<{ delay?: number }>(), { delay: 0 })

const shown = ref(false)

onMounted(() => {
  // 等一帧让初始态先渲染，再加 class 才能触发过渡
  requestAnimationFrame(() => (shown.value = true))
})
</script>

<template>
  <div class="fade-content" :class="{ shown }" :style="{ transitionDelay: `${delay}ms` }">
    <slot />
  </div>
</template>

<style scoped>
.fade-content {
  opacity: 0;
  transform: translateY(4px);
  transition:
    opacity 160ms ease-out,
    transform 160ms ease-out;
}
.fade-content.shown {
  opacity: 1;
  transform: none;
}
@media (prefers-reduced-motion: reduce) {
  .fade-content {
    opacity: 1;
    transform: none;
    transition: none;
  }
}
</style>
