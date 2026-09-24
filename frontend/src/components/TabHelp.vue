<script setup lang="ts">
import { computed } from 'vue'
import { NPopover } from 'naive-ui'
import { useI18n } from 'vue-i18n'

/**
 * tab 头部右侧的圆形问号帮助按钮（Artemis Instructions 风格）。
 * 内容取 i18n 的 help.<topic>：title + lines[]（多段说明，随语言切换）。
 */
const props = defineProps<{ topic: string }>()
const { t, te } = useI18n()

const title = computed(() =>
  te(`help.${props.topic}.title`) ? t(`help.${props.topic}.title`) : t('help.default.title'))
const lines = computed<string[]>(() =>
  te(`help.${props.topic}.lines`) ? t(`help.${props.topic}.lines`).split('\n') : [])
</script>

<template>
  <n-popover trigger="click" placement="bottom-end" :style="{ maxWidth: '520px' }">
    <template #trigger>
      <span class="help-btn" :title="$t('help.default.title')">?</span>
    </template>
    <div class="help-panel">
      <div class="help-title">{{ title }}</div>
      <p v-for="(line, i) in lines" :key="i" class="help-line">{{ line }}</p>
    </div>
  </n-popover>
</template>

<style scoped>
.help-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid #0b63ce;
  color: #0b63ce;
  font-size: 12px;
  font-weight: 700;
  cursor: help;
  user-select: none;
  flex: none;
}
.help-panel {
  max-width: 460px;
}
.help-title {
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #efeff5;
}
.help-line {
  font-size: 13px;
  color: #333;
  line-height: 1.6;
  margin: 6px 0;
}
</style>
