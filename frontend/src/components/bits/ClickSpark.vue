<script setup lang="ts">
/** 点击粒子迸发（ui-upgrade-design.md §5.2⑤，L1 反馈，手写 CSS）。
 *  仅包裹危险操作按钮（删除确认 / SSH 执行确认），严禁做成全局点击效果。
 *  粒子渲染在 body 下的 fixed 层（z-index 3000），保证盖过 n-modal；
 *  单个 keyframes + 每粒子 --dx/--dy 随机方向，animationend 自移除。 */
import { ref } from 'vue'

interface Particle {
  id: number
  x: number
  y: number
  dx: number
  dy: number
}

const particles = ref<Particle[]>([])
let seq = 0

// reduced-motion 直接不生成粒子（position tracking 不涉及，粒子纯动效）
const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

function onClick(e: MouseEvent) {
  if (reduced) return
  // ponytail: 并发上限按粒子数计（8/组，≥24 即已有 3 组活跃），免维护 burst 计数
  if (particles.value.length >= 24) return
  const { clientX: x, clientY: y } = e
  for (let i = 0; i < 8; i++) {
    const angle = Math.random() * Math.PI * 2
    const dist = 18 + Math.random() * 10
    particles.value.push({ id: seq++, x, y, dx: Math.cos(angle) * dist, dy: Math.sin(angle) * dist })
  }
}

function done(id: number) {
  particles.value = particles.value.filter((p) => p.id !== id)
}
</script>

<template>
  <!-- 透明包裹层：inline-flex + line-height 0，保证按钮布局零位移 -->
  <span class="spark-wrap" @click="onClick"><slot /></span>
  <Teleport to="body">
    <span
      v-for="p in particles"
      :key="p.id"
      class="spark-p"
      :style="{ left: `${p.x}px`, top: `${p.y}px`, '--dx': `${p.dx}px`, '--dy': `${p.dy}px` }"
      @animationend="done(p.id)"
    />
  </Teleport>
</template>

<style scoped>
.spark-wrap {
  display: inline-flex;
  line-height: 0;
}
.spark-p {
  position: fixed;
  z-index: 3000;
  width: 3px;
  height: 3px;
  margin: -1.5px 0 0 -1.5px; /* 以点击点为圆心 */
  border-radius: 50%;
  background: var(--ops-primary, #d03050);
  pointer-events: none;
  animation: spark-fly 320ms ease-out forwards;
}
@keyframes spark-fly {
  to {
    transform: translate(var(--dx), var(--dy)) scale(0.3);
    opacity: 0;
  }
}
</style>
