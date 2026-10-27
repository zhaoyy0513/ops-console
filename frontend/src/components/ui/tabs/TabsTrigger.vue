<script setup lang="ts">
import { TabsTrigger } from 'reka-ui'
import { cn } from '@/lib/utils'
const props = defineProps<{ value: string; class?: string; disabled?: boolean }>()
</script>
<template>
  <TabsTrigger
    :value="value"
    :disabled="disabled"
    :class="
      cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-sm px-2.5 h-7 text-xs font-medium transition-colors cursor-pointer data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground hover:text-foreground',
        props.class,
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>
