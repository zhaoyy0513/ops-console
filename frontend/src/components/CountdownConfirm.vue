<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NCard, NModal } from 'naive-ui'

/**
 * 危险操作倒计时确认框（PRD §11.5）。
 * 倒计时只是 UI 防误操作机制，不是安全机制——后端以操作白名单 + oplog 兜底。
 */
const props = defineProps<{
  label: string
  target: string
  seconds?: number
  confirmText?: string
  width?: string
}>()
const emit = defineEmits<{ (e: 'confirm'): void }>()

const show = ref(false)
const remaining = ref(props.seconds ?? 5)

watch(show, (v) => {
  if (v) remaining.value = props.seconds ?? 5
})

// 每秒递减，归零停表（setInterval 句柄即开即弃）
let timer: ReturnType<typeof setInterval> | null = null
watch(show, (v) => {
  if (timer) clearInterval(timer)
  if (v) {
    timer = setInterval(() => {
      if (remaining.value > 0) remaining.value--
      if (remaining.value <= 0 && timer) {
        clearInterval(timer)
        timer = null
      }
    }, 1000)
  }
})
</script>

<template>
  <!-- 触发按钮与 Save 同规格（small 实心红），风格统一 -->
  <n-button size="small" type="error" :style="width ? { width } : undefined" @click="show = true">{{ label }}</n-button>
  <n-modal v-model:show="show">
    <n-card style="width: 440px" title="危险操作确认" size="small" :bordered="false">
      <p>You are about to delete:</p>
      <p style="font-family: ui-monospace, monospace; font-weight: 600">{{ target }}</p>
      <p style="color: #d03050">This operation cannot be undone.</p>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span v-if="remaining > 0" style="color: #999">Please wait {{ remaining }}s...</span>
          <span v-else style="color: #999">按钮已解锁</span>
          <div style="display: flex; gap: 8px">
            <n-button size="small" @click="show = false">取消</n-button>
            <n-button size="small" type="error" :disabled="remaining > 0"
              @click="((show = false), emit('confirm'))">
              {{ confirmText ?? 'Delete' }}
            </n-button>
          </div>
        </div>
      </template>
    </n-card>
  </n-modal>
</template>
