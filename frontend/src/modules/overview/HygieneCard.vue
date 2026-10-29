<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { overviewApi, type HygieneIssue } from './api'

const props = defineProps<{ siteId: string }>()
const { t, te } = useI18n()

const issues = ref<HygieneIssue[]>([])
const error = ref('')

async function load() {
  if (!props.siteId) return
  error.value = ''
  try {
    issues.value = await overviewApi.hygiene(props.siteId)
  } catch (e) {
    issues.value = []
    error.value = (e as Error).message
  }
}

onMounted(load)
watch(() => props.siteId, load)

/** i18n 缺 key 时退回后端 detail，避免裸 key */
function tip(i: HygieneIssue): string {
  const key = `overview.hygieneTips.${i.type}`
  return te(key) ? t(key) : i.detail
}

function typeLabel(rt: string): string {
  const key = `tabs.${rt}`
  return te(key) ? t(key) : rt
}
</script>

<template>
  <!-- 有问题（或读取失败）才占位，健康站点不打扰 -->
  <Card v-if="error || issues.length">
    <CardHeader><CardTitle>{{ t('overview.hygiene') }}</CardTitle></CardHeader>
    <CardContent>
      <p v-if="error" class="text-sm text-muted-foreground">
        {{ t('overview.hygieneFailed') }}: {{ error }}
      </p>
      <ul v-else class="hyg-list">
        <li v-for="(i, idx) in issues" :key="idx" class="hyg-row">
          <span class="hyg-dot" :class="i.severity" />
          <span class="hyg-res">{{ typeLabel(i.resource_type) }}/{{ i.resource_name }}</span>
          <span class="hyg-tip">— {{ tip(i) }}</span>
        </li>
      </ul>
    </CardContent>
  </Card>
</template>

<style scoped>
.hyg-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hyg-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 0.875rem;
}
.hyg-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  align-self: center;
}
.hyg-dot.warning {
  background: var(--ops-warning);
}
.hyg-dot.info {
  background: var(--ops-unknown);
}
.hyg-res {
  font-weight: 500;
  white-space: nowrap;
}
.hyg-tip {
  color: var(--muted-foreground);
}
</style>
