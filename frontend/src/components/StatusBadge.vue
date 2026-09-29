<script setup lang="ts">
import { computed } from 'vue'
import { NTag } from 'naive-ui'

const props = defineProps<{ status?: string | null }>()

const map: Record<string, { label: string; type: 'success' | 'warning' | 'error' | 'default'; dot: string }> = {
  HEALTHY: { label: 'Healthy', type: 'success', dot: 'var(--ops-healthy)' },
  STARTED: { label: 'Started', type: 'success', dot: 'var(--ops-healthy)' },
  WARNING: { label: 'Warning', type: 'warning', dot: 'var(--ops-warning)' },
  CRITICAL: { label: 'Critical', type: 'error', dot: 'var(--ops-critical)' },
}
const info = computed(() => map[props.status ?? ''] ?? { label: 'Unknown', type: 'default', dot: 'var(--ops-unknown)' })
</script>

<template>
  <span class="status-badge">
    <span class="dot" :class="{ pulse: info.type === 'error' }" :style="{ background: info.dot }" />
    <n-tag :type="info.type" size="small" round :bordered="false">{{ info.label }}</n-tag>
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.dot.pulse {
  animation: ops-breathe 1.6s ease-in-out infinite;
}
@keyframes ops-breathe {
  50% { opacity: 0.35; }
}
</style>
