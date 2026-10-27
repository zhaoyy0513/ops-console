<script setup lang="ts">
import { TabsList } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps<{ class?: string }>()
</script>
<template>
  <TabsList :class="cn('inline-flex h-8 items-center gap-1 rounded-md bg-secondary p-0.5', props.class)">
    <slot />
  </TabsList>
</template>
