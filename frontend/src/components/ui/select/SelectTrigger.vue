<script setup lang="ts">
import { SelectTrigger as RTrigger, SelectValue } from 'reka-ui'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })
const props = defineProps<{ placeholder?: string; class?: string }>()
</script>

<template>
  <RTrigger
    :class="
      cn(
        'flex h-8 items-center justify-between gap-2 rounded-md border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus:border-ring focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:truncate cursor-pointer',
        props.class ?? 'w-full',
      )
    "
  >
    <SelectValue :placeholder="placeholder" />
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      class="opacity-60 shrink-0"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  </RTrigger>
</template>
