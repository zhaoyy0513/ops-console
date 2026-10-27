<script setup lang="ts">
import { SelectContent, SelectPortal, SelectViewport } from 'reka-ui'
</script>

<template>
  <SelectPortal>
    <SelectContent
      position="popper"
      :side-offset="4"
      class="z-50 max-h-72 min-w-[8rem] overflow-hidden rounded-lg border border-border bg-popover p-1 shadow-md"
    >
      <SelectViewport class="p-0">
        <slot />
      </SelectViewport>
    </SelectContent>
  </SelectPortal>
</template>
