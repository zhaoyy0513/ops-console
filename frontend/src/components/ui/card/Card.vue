<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<template>
  <!-- 描边卡：不透明面 + hairline 描边（三份 brief 都是描边卡；投影走 token，当前为 none） -->
  <div
    :class="cn('flex flex-col rounded-xl border text-card-foreground border-[color:var(--ops-card-border)] bg-card shadow-[var(--ops-shadow-card)] [backdrop-filter:blur(var(--ops-blur-card))]', props.class)"
  >
    <slot />
  </div>
</template>
