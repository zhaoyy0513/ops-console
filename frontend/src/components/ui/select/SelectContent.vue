<script setup lang="ts">
import { SelectContent, SelectPortal, SelectViewport } from 'reka-ui'
</script>

<template>
  <SelectPortal>
    <SelectContent
      position="popper"
      :side-offset="4"
      class="z-50 max-h-72 min-w-[8rem] overflow-hidden rounded-lg border border-[color:var(--ops-card-border)] bg-[color:var(--ops-dialog)] p-1 shadow-md [backdrop-filter:blur(var(--ops-blur-card))]"
    >
      <SelectViewport class="p-0">
        <slot />
      </SelectViewport>
    </SelectContent>
  </SelectPortal>
</template>
