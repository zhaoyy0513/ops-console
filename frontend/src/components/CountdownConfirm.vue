<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from 'lucide-vue-next'
import { AlertDialog } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { AlertDialogContent as RContent, AlertDialogOverlay, AlertDialogTitle } from 'reka-ui'
import ClickSpark from './bits/ClickSpark.vue'

/**
 * 危险操作倒计时确认框（PRD §11.5）。
 * 倒计时只是 UI 防误操作机制，不是安全机制——后端以操作白名单 + oplog 兜底。
 * onConfirm 返回 Promise：确认按钮 pending 置灰防连点（清空队列/kill 等 in-flight 保护）。
 */
const { t } = useI18n()
const props = defineProps<{
  label: string
  target: string
  seconds?: number // 解锁倒计时秒数，默认 3
  confirmText?: string
  width?: string
  onConfirm?: () => Promise<unknown> | void
}>()

const show = ref(false)
const remaining = ref(props.seconds ?? 3)
/** 确认执行中：按钮禁用 + 转圈，防连点重复触发（onConfirm 返回 Promise 才能感知完成）。
 *  成功路径保持锁定直到下次打开弹窗（避免极快的响应窗口内被连点第二次）；失败才解锁允许重试。 */
const pending = ref(false)

async function onConfirmClick() {
  if (pending.value) return
  pending.value = true
  try {
    await props.onConfirm?.()
    show.value = false // 成功后保持 pending，直到下次打开时复位
  } catch {
    pending.value = false
  }
}

watch(show, (v) => {
  if (v) {
    remaining.value = props.seconds ?? 3
    pending.value = false // 每次重新打开复位执行锁
  }
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
// 组件卸载时兜底清表（如倒计时中途路由切走）
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

/** Escape / 遮罩点击不得关窗（对齐原 n-modal mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}
</script>

<template>
  <!-- 触发按钮与 Save 同规格（small 实心红），风格统一；ClickSpark 仅此危险按钮 -->
  <ClickSpark>
    <Button variant="destructive" size="sm" :style="width ? { width } : undefined" @click="show = true">{{
      label
    }}</Button>
  </ClickSpark>
  <!-- 确认弹窗 Teleport 到 body：玻璃主题的 Card 带 backdrop-filter（毛玻璃），
       会使内部 fixed 元素以卡片为包含块（遮罩只盖卡片、弹窗钉在卡片内）。
       teleport 回视口基准，任何祖先的 transform/filter/backdrop-filter 都不再影响；
       触发按钮仍就地渲染（表格单元格内点击）。 -->
  <AlertDialog v-model:open="show">
    <Teleport to="body">
      <AlertDialogOverlay class="fixed inset-0 z-50 bg-black/35" @interact-outside="blockDismiss" />
      <RContent
        role="alertdialog"
        :aria-describedby="undefined"
        class="fixed left-1/2 top-1/2 z-50 w-[440px] max-w-[92vw] -translate-x-1/2 -translate-y-1/2 gap-4 border border-border backdrop-blur-md bg-[color:var(--ops-dialog)] p-5 shadow-lg"
        @escape-key-down="blockDismiss"
        @interact-outside="blockDismiss"
      >
        <div class="flex flex-col gap-3">
          <AlertDialogTitle class="text-base font-semibold">{{ t('countdown.title') }}</AlertDialogTitle>
          <p class="text-sm text-muted-foreground">{{ t('countdown.about') }}</p>
          <p class="font-mono text-sm font-semibold break-all">{{ target }}</p>
          <p class="text-sm font-medium" style="color: var(--destructive)">{{ t('countdown.warn') }}</p>
        </div>
        <div class="flex items-center justify-between gap-3 pt-3">
          <span v-if="remaining > 0" class="text-xs text-muted-foreground">{{
            t('countdown.waiting', { n: remaining })
          }}</span>
          <span v-else class="text-xs text-muted-foreground">{{ t('countdown.unlocked') }}</span>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" :disabled="pending" @click="show = false">{{ t('common.cancel') }}</Button>
            <Button variant="destructive" size="sm" :disabled="remaining > 0 || pending" @click="onConfirmClick">
              <LoaderCircle v-if="pending" class="animate-spin" />
              {{ confirmText ?? t('common.delete') }}
            </Button>
          </div>
        </div>
      </RContent>
    </Teleport>
  </AlertDialog>
</template>
