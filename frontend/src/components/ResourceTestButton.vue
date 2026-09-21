<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NSpace, NTag } from 'naive-ui'
import api from '../api'

const props = defineProps<{
  /** 资源类型：server | redis | mq | robot */
  type: string
  /** 连接配置（表单当前值或已存完整配置，含密码） */
  config: Record<string, unknown>
}>()

interface TestResult {
  success: boolean
  latency_ms: number
  message: string
}

const loading = ref(false)
const result = ref<TestResult | null>(null)

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
    <n-button size="small" :loading="loading" @click="run">Test</n-button>
    <n-tag v-if="result" :type="result.success ? 'success' : 'error'" size="small" :bordered="false">
      {{ result.success ? 'OK' : 'FAILED' }} · {{ result.message }} ({{ result.latency_ms }}ms)
    </n-tag>
  </n-space>
</template>
