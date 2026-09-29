<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon, NSpace, NTag, NTooltip } from 'naive-ui'
import { CheckmarkCircleOutline, CloseCircleOutline } from '@vicons/ionicons5'
import { i18n } from '../i18n'
import api from '../api'

const props = defineProps<{
  /** 资源类型：server | redis | mq | robot */
  type: string
  /** 连接配置（表单当前值或已存完整配置，含密码） */
  config: Record<string, unknown>
}>()

// 直接用全局 i18n（测试环境不装插件也能挂载）；composer.t 对 locale 变化是响应式的
const t = i18n.global.t

interface TestResult {
  success: boolean
  latency_ms: number
  message: string
}

const loading = ref(false)
const result = ref<TestResult | null>(null)

/** 标签内只显示短摘要（如剥掉 "SSH connect failed: " 前缀），全文在 tooltip */
const shortMessage = computed(() => {
  const m = result.value?.message ?? ''
  const stripped = m.replace(/^SSH connect failed:\s*/, '').replace(/^Redis (connect|query) failed:\s*/, '')
  return stripped.length > 40 ? `${stripped.slice(0, 40)}…` : stripped
})

async function run() {
  loading.value = true
  result.value = null
  try {
    result.value = (await api.post('/test-connection', {
      type: props.type,
      config: props.config,
    })) as unknown as TestResult
  } catch (e) {
    result.value = { success: false, latency_ms: 0, message: (e as Error).message }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <n-space align="center" :size="8" :wrap="false">
    <n-button size="small" :loading="loading" @click="run">{{ t('common.test') }}</n-button>
    <n-tooltip v-if="result" trigger="hover">
      <template #trigger>
        <n-tag
          class="result-tag"
          :class="{ shake: !result.success }"
          :type="result.success ? 'success' : 'error'"
          size="small"
          :bordered="false"
        >
          <span class="result-inner">
            <n-icon :component="result.success ? CheckmarkCircleOutline : CloseCircleOutline" />
            {{ result.success ? 'OK' : 'FAILED' }} · {{ shortMessage }}
            <span class="latency">{{ result.latency_ms }}ms</span>
          </span>
        </n-tag>
      </template>
      {{ result.message }} <!-- 悬浮看全文，标签内截断不撑破弹窗 -->
    </n-tooltip>
  </n-space>
</template>

<style scoped>
.result-tag {
  max-width: 280px;
}
.result-tag :deep(.n-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-inner {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
/* latency 等宽：数字刷新时宽度不抖 */
.latency {
  font-family: var(--ops-font-mono);
  font-variant-numeric: tabular-nums;
}
/* 失败轻微抖动（L1 反馈，120ms 一次性） */
.shake {
  animation: ops-shake 120ms ease-in-out 2;
}
@keyframes ops-shake {
  25% { transform: translateX(-2px); }
  75% { transform: translateX(2px); }
}
@media (prefers-reduced-motion: reduce) {
  .shake { animation: none; }
}
</style>
