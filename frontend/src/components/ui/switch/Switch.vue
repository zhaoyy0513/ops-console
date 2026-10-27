<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { cn } from '@/lib/utils'

const model = defineModel<boolean>({ default: false })
const props = defineProps<{ disabled?: boolean; class?: string }>()
</script>

<template>
  <SwitchRoot
    v-model="model"
    :disabled="disabled"
    :class="
      cn(
        'inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full p-0.5 transition-colors data-[state=checked]:bg-primary data-[state=unchecked]:bg-input data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50',
        props.class,
      )
    "
  >
    <SwitchThumb
      class="pointer-events-none block size-3.5 rounded-full bg-background shadow-sm transition-transform data-[state=checked]:translate-x-[14px] data-[state=unchecked]:translate-x-0"
    />
  </SwitchRoot>
</template>
