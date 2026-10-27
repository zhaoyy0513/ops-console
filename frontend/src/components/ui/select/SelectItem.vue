<script setup lang="ts">
import { SelectItem, SelectItemIndicator, SelectItemText } from 'reka-ui'
import { Check } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const props = defineProps<{
  value: string
  class?: string
  disabled?: boolean
}>()
</script>

<template>
  <SelectItem
    :value="value"
    :disabled="disabled"
    :class="
      cn(
        'relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-7 pr-2 text-sm outline-none data-[highlighted]:bg-accent data-[disabled]:opacity-50',
        props.class,
      )
    "
  >
    <SelectItemIndicator class="absolute left-2 flex size-3.5 items-center justify-center">
      <Check class="size-3.5" />
    </SelectItemIndicator>
    <SelectItemText><slot /></SelectItemText>
  </SelectItem>
</template>
