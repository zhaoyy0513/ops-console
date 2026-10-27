<script setup lang="ts">
import {
  AlertDialogContent,
  AlertDialogOverlay,
  AlertDialogPortal,
} from 'reka-ui'

defineProps<{
  /** 'action' 红色确认 / 'cancel' 灰色取消 */
  kind?: 'action' | 'cancel'
}>()
</script>

<template>
  <AlertDialogPortal>
    <AlertDialogOverlay class="fixed inset-0 z-50 bg-black/60" />
    <AlertDialogContent
      :aria-describedby="undefined"
      class="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 gap-4 border border-border bg-card p-5 shadow-lg"
    >
      <slot />
    </AlertDialogContent>
  </AlertDialogPortal>
</template>
