<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { TooltipRoot, TooltipTrigger } from 'reka-ui'
import TooltipContent from '@/components/ui/tooltip/TooltipContent.vue'
import { message } from '@/lib/message'

const props = withDefaults(defineProps<{ text: string; max?: number; copy?: boolean }>(), {
  max: 200,
  copy: true,
})

const { t } = useI18n()
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
  <TooltipRoot :delay-duration="100" :disable-hoverable-content="!copy" :disabled="!hasText">
    <TooltipTrigger as-child>
      <span class="tip-copy" :style="{ maxWidth: `${max}px` }">{{ text || '-' }}</span>
    </TooltipTrigger>
    <TooltipContent class="max-w-md" :side-offset="6">
      <div class="tip-copy-pop">
        <span class="tip-copy-full">{{ text }}</span>
        <button
          v-if="copy"
          type="button"
          class="tip-copy-btn flex-none cursor-pointer rounded px-1.5 py-0.5 text-xs text-popover-foreground/85 hover:bg-popover-foreground/10 hover:text-popover-foreground"
          @click="copy"
        >
          {{ t('common.copy') }}
        </button>
      </div>
    </TooltipContent>
  </TooltipRoot>
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
/* 复制按钮走 popover 语义 token（ui/tooltip 的 TooltipContent 默认类已带
   bg-popover text-popover-foreground），三套画风下底色/文字对比度都成立 */
.tip-copy-btn {
  margin-top: 2px;
}
</style>
