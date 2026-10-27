<script setup lang="ts">
import { cn } from '@/lib/utils'

const props = defineProps<{ class?: string; rows?: number }>()
const model = defineModel<string>({ default: '' })
</script>

<template>
  <textarea
    v-model="model"
    :rows="rows ?? 3"
    :class="
      cn(
        'flex min-h-16 w-full rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50',
        props.class,
      )
    "
  />
</template>
