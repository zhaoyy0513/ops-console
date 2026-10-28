<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<template>
  <!-- 页面/区块标题统一紫粉渐变文字（.ops-gradient-text 见 style.css；弹窗标题走 DialogTitle 不受影响） -->
  <h3 :class="cn('ops-gradient-text text-[15px] font-semibold leading-none tracking-tight', props.class)"><slot /></h3>
</template>
