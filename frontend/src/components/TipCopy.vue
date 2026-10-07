<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NTooltip, useMessage } from 'naive-ui'

const props = withDefaults(defineProps<{ text: string; max?: number; copy?: boolean }>(), {
  max: 200,
  copy: true,
})

const { t } = useI18n()
const message = useMessage()
const hasText = computed(() => props.text.length > 0)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    message.success(t('common.copied'))
  } catch {
    /* clipboard unavailable — fail silently */
  }
}
</script>

<template>
  <n-tooltip :disabled="!hasText" trigger="hover">
    <template #trigger>
      <span class="tip-copy" :style="{ maxWidth: `${max}px` }">{{ text || '-' }}</span>
    </template>
    <div class="tip-copy-pop">
      <span class="tip-copy-full">{{ text }}</span>
      <n-button v-if="copy" class="tip-copy-btn" size="tiny" quaternary :bordered="false" @click="copy">
        {{ t('common.copy') }}
      </n-button>
    </div>
  </n-tooltip>
</template>

<style scoped>
/* 截断触发器：单元格内省略号，全文走 tooltip */
.tip-copy {
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
/* tooltip 内容挂在 body 下的 popover：naive tooltip 浅/深主题都是深底，
   文字/按钮一律用白色系；不用 --ops-text-*（页面底色 token，深底上会隐形）。
   n-tooltip 内容默认可悬停（跟随 popover 行为），移入浮层/按钮不会关闭 */
.tip-copy-pop {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 420px;
}
.tip-copy-full {
  flex: 1;
  min-width: 0;
  word-break: break-all;
  white-space: pre-wrap;
  max-height: 200px;
  overflow: auto;
}
/* quaternary 无边框无底色；!important 压过 naive 写在根元素上的内联主题变量 */
.tip-copy-btn {
  flex: none;
  --n-text-color: rgba(255, 255, 255, 0.85) !important;
  --n-text-color-hover: #fff !important;
  --n-text-color-pressed: #fff !important;
  --n-text-color-focus: #fff !important;
  --n-color-hover: rgba(255, 255, 255, 0.12) !important;
  --n-color-pressed: rgba(255, 255, 255, 0.2) !important;
  --n-color-focus: rgba(255, 255, 255, 0.12) !important;
}
.tip-copy-btn:focus-visible {
  outline: 1px solid rgba(255, 255, 255, 0.6);
  outline-offset: 1px;
}
</style>
