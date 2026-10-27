<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'

const props = defineProps<{ status?: string | null }>()

const map: Record<string, { label: string; variant: 'success' | 'warning' | 'critical'; dot: string }> = {
  HEALTHY: { label: 'Healthy', variant: 'success', dot: 'var(--ops-healthy)' },
  STARTED: { label: 'Started', variant: 'success', dot: 'var(--ops-healthy)' },
  WARNING: { label: 'Warning', variant: 'warning', dot: 'var(--ops-warning)' },
  CRITICAL: { label: 'Critical', variant: 'critical', dot: 'var(--ops-critical)' },
}
const info = computed(() => map[props.status ?? ''] ?? { label: 'Unknown', variant: 'outline' as const, dot: 'var(--ops-unknown)' })
</script>

<template>
  <span class="status-badge">
    <span class="dot" :class="{ pulse: info.variant === 'critical' }" :style="{ background: info.dot }" />
    <Badge :variant="info.variant" size="sm">{{ info.label }}</Badge>
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
