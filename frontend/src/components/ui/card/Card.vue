<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<template>
  <!-- 玻璃拟态卡片：--card 半透明白（tokens）+ blur + 白描边 + 柔投影（spec：blur 12px / 白 60% 描边 / 0 4px 16px 4% 投影） -->
  <div
    :class="cn('flex flex-col rounded-xl border backdrop-blur-md text-card-foreground border-[color:var(--ops-card-border)] bg-card shadow-[var(--ops-shadow-card)]', props.class)"
  >
    <slot />
  </div>
</template>
