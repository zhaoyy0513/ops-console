<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'

defineProps<{
  /** 主文案 */
  title: string
  /** 副文案（可选） */
  desc?: string
}>()
</script>

<template>
  <div class="empty-state">
    <Inbox class="empty-icon size-9" :stroke-width="1.5" />
    <div class="empty-title">{{ title }}</div>
    <div v-if="desc" class="empty-desc">{{ desc }}</div>
    <slot />
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 0;
}
.empty-icon {
  color: var(--ops-text-3);
  opacity: 0.6;
}
.empty-title {
  font-size: 13px;
  color: var(--ops-text-2);
}
.empty-desc {
  font-size: 12px;
  color: var(--ops-text-3);
}
</style>
