<script setup lang="ts">
import { NTag } from 'naive-ui'
import { computed } from 'vue'

const props = defineProps<{ status?: string | null }>()

const map: Record<string, { label: string; type: 'success' | 'warning' | 'error' | 'default' }> = {
  HEALTHY: { label: 'Healthy', type: 'success' },
  WARNING: { label: 'Warning', type: 'warning' },
  CRITICAL: { label: 'Critical', type: 'error' },
}
const info = computed(() => map[props.status ?? ''] ?? { label: 'Unknown', type: 'default' })
</script>

<template>
  <n-tag :type="info.type" size="small" round :bordered="false">{{ info.label }}</n-tag>
</template>
