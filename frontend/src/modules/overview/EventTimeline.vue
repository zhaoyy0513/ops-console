<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { overviewApi, type SiteEvent } from './api'

const props = defineProps<{ siteId: string }>()
const { t, te } = useI18n()

const events = ref<SiteEvent[]>([])
const error = ref('')

// 事件类型徽标色：诊断/重启偏警示，配置中性，网络绿色
const KIND_VARIANT: Record<string, 'warning' | 'critical' | 'outline' | 'success'> = {
  diag: 'warning',
  restart: 'critical',
  config: 'outline',
  net: 'success',
}

async function load() {
  if (!props.siteId) return
  error.value = ''
  try {
    events.value = await overviewApi.events(props.siteId, 50)
  } catch (e) {
    events.value = []
    error.value = (e as Error).message
  }
}

onMounted(load)
watch(() => props.siteId, load)

function kindLabel(kind: string): string {
  const key = `overview.eventKinds.${kind}`
  return te(key) ? t(key) : kind
}

function fmtTime(iso: string): string {
  return iso ? iso.replace('T', ' ').slice(5, 19) : '-'
}
</script>

<template>
  <Card>
    <CardHeader><CardTitle>{{ t('overview.events') }}</CardTitle></CardHeader>
    <CardContent>
      <p v-if="error" class="text-sm text-muted-foreground">
        {{ t('overview.eventsFailed') }}: {{ error }}
      </p>
      <ul v-else-if="events.length" class="ev-list">
        <li v-for="(e, idx) in events" :key="idx" class="ev-row">
          <span class="ev-time">{{ fmtTime(e.time) }}</span>
          <Badge :variant="KIND_VARIANT[e.kind] ?? 'outline'" size="sm">{{ kindLabel(e.kind) }}</Badge>
          <span class="ev-title" :title="e.detail || e.title">{{ e.title }}</span>
        </li>
      </ul>
      <p v-else class="text-sm text-muted-foreground">{{ t('overview.noEvents') }}</p>
    </CardContent>
  </Card>
</template>

<style scoped>
.ev-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ev-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
}
.ev-time {
  flex: none;
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--muted-foreground);
}
.ev-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
