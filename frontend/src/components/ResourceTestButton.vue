<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'
import { TooltipContent } from '@/components/ui/tooltip'
import { CircleCheck, CircleX, LoaderCircle } from 'lucide-vue-next'
import { i18n } from '../i18n'
import api from '../api'

const props = defineProps<{
  /** 资源类型：server | redis | mq | device */
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
  <div class="inline-flex items-center gap-2">
    <Button variant="outline" size="sm" :disabled="loading" @click="run">
      <LoaderCircle v-if="loading" class="size-3.5 animate-spin" />
      {{ t('common.test') }}
    </Button>
    <TooltipProvider>
      <TooltipRoot v-if="result">
        <TooltipTrigger as-child>
          <Badge
            class="max-w-[280px] cursor-default"
            :class="{ shake: !result.success }"
            :variant="result.success ? 'success' : 'critical'"
          >
            <span class="result-inner min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
              <component :is="result.success ? CircleCheck : CircleX" class="size-3 shrink-0" />
              {{ result.success ? 'OK' : 'FAILED' }} · {{ shortMessage }}
              <span class="latency">{{ result.latency_ms }}ms</span>
            </span>
          </Badge>
        </TooltipTrigger>
        <TooltipContent class="max-w-sm whitespace-pre-wrap break-all">
          <!-- 悬浮看全文，标签内截断不撑破弹窗 -->
          {{ result.message }}
        </TooltipContent>
      </TooltipRoot>
    </TooltipProvider>
  </div>
</template>

<style scoped>
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
