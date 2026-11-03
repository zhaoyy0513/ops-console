<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<template>
  <!-- 页面/区块标题：各主题 --ops-gradient-text 着色（旧三主题渐变、新三主题调色板内色） -->
  <h3 :class="cn('ops-gradient-text text-[15px] font-semibold leading-none tracking-tight', props.class)"><slot /></h3>
</template>
