<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  type DialogContentEmits,
  type DialogContentProps,
  useForwardPropsEmits,
} from 'reka-ui'
import { X } from 'lucide-vue-next'
import type { HTMLAttributes } from 'vue'
import { cn } from '@/lib/utils'

const props = defineProps<DialogContentProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<DialogContentEmits>()
const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DialogPortal>
    <DialogOverlay class="fixed inset-0 z-50 bg-black/35 backdrop-blur-[2px]" />
    <DialogContent
      v-bind="forwarded"
      :aria-describedby="undefined"
      :class="
        cn(
          'fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border backdrop-blur-md border-[color:var(--ops-card-border)] bg-[color:var(--ops-dialog)] p-6 shadow-xl max-h-[85vh] overflow-y-auto',
          props.class,
        )
      "
    >
      <slot />
      <DialogClose
        class="absolute right-4 top-4 opacity-60 transition-opacity hover:opacity-100 cursor-pointer"
      >
        <X class="size-4" />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
