<script setup lang="ts">
import { DialogTitle } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

// 必须用 reka 的 DialogTitle（渲染 id + aria-labelledby 关联到 DialogContent）——
// 普通 h2 会让每个弹窗都报 "requires a DialogTitle" 无障碍警告
const props = defineProps<{ class?: HTMLAttributes['class'] }>()
</script>
<template>
  <DialogTitle :class="cn('text-base font-semibold leading-none', props.class)"><slot /></DialogTitle>
</template>
