<script setup lang="ts">
import { TabsContent } from 'reka-ui'
const props = defineProps<{ value: string; class?: string }>()
</script>
<template>
  <TabsContent :value="value" :class="props.class"><slot /></TabsContent>
</template>
