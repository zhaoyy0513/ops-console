<script setup lang="ts">
import { NIcon } from 'naive-ui'
import { FileTrayOutline } from '@vicons/ionicons5'

defineProps<{
  /** 主文案 */
  title: string
  /** 副文案（可选） */
  desc?: string
}>()
</script>

<template>
  <div class="empty-state">
    <n-icon :size="36" class="empty-icon"><FileTrayOutline /></n-icon>
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
