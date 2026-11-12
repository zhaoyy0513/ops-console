<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircle2, Download, LoaderCircle, X } from 'lucide-vue-next'
import { Progress } from '@/components/ui/progress'
import { humanSize } from './api'
import type { KnowledgeDownloadTask } from './useKnowledgeDownload'

const props = defineProps<{ tasks: KnowledgeDownloadTask[] }>()
const emit = defineEmits<{ (e: 'remove', id: string): void; (e: 'clear'): void }>()
const { t } = useI18n()

const visible = computed(() => props.tasks.length > 0)

function pct(task: KnowledgeDownloadTask): number {
  return task.total > 0 ? Math.min(100, Math.round((task.loaded / task.total) * 100)) : 0
}

function statusText(task: KnowledgeDownloadTask): string {
  if (task.status === 'preparing') return t('knowledge.preparing')
  if (task.status === 'downloading') {
    return `${humanSize(task.loaded)} / ${humanSize(task.total)} · ${pct(task)}%`
  }
  if (task.status === 'done') return t('knowledge.savedTo', { folder: task.folderName ?? '' })
  return task.error ?? t('knowledge.downloadFailed')
}
</script>

<template>
  <div v-if="visible" class="download-panel">
    <div class="dp-head">
      <span class="dp-title">
        <Download class="size-3.5" />
        {{ $t('knowledge.downloadProgress') }}
      </span>
      <button type="button" class="dp-clear" @click="emit('clear')">{{ $t('knowledge.clearDone') }}</button>
    </div>

    <div v-for="task in tasks" :key="task.id" class="dp-item">
      <div class="dp-row">
        <span class="dp-name" :title="task.filename">{{ task.filename }}</span>
        <button type="button" class="dp-close" @click="emit('remove', task.id)">
          <X class="size-3.5" />
        </button>
      </div>
      <Progress :value="pct(task)" class="h-1.5" />
      <div class="dp-meta">
        <LoaderCircle v-if="task.status === 'downloading' || task.status === 'preparing'" class="size-3 animate-spin" />
        <CheckCircle2 v-else-if="task.status === 'done'" class="size-3 text-green-600" />
        <span class="truncate">{{ statusText(task) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.download-panel {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 900;
  width: 320px;
  max-width: calc(100vw - 32px);
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  background: var(--ops-surface);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}
.dp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.dp-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ops-text-1);
}
.dp-clear {
  border: none;
  background: transparent;
  color: var(--primary);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}
.dp-clear:hover {
  text-decoration: underline;
}
.dp-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-s);
  background: var(--ops-surface-2);
}
.dp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.dp-name {
  min-width: 0;
  flex: 1;
  font-size: 12px;
  color: var(--ops-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dp-close {
  border: none;
  background: transparent;
  color: var(--ops-text-3);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
}
.dp-close:hover {
  background: var(--ops-muted);
  color: var(--ops-text-1);
}
.dp-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ops-text-3);
  font-variant-numeric: tabular-nums;
}
</style>
