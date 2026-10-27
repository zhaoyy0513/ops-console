<script setup lang="ts">
import { AlertDialogAction } from 'reka-ui'
import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'

const props = defineProps<{ class?: string; variant?: 'default' | 'destructive' }>()
</script>

<template>
  <AlertDialogAction :class="cn(buttonVariants({ variant: variant ?? 'destructive' }), props.class)">
    <slot />
  </AlertDialogAction>
</template>
