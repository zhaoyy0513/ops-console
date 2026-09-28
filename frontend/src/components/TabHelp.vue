<script setup lang="ts">
import { computed, ref } from 'vue'
import { NModal } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { helpContent, type HelpSection } from '../i18n/help'

/**
 * tab 头部右侧的圆形问号帮助按钮（Artemis console Instructions 风格）。
 * 点击弹出模态说明（标题栏 + 逐条编号说明）；内容按 locale 直接读
 * i18n/help.ts 的 helpContent（不经过 vue-i18n messages）。
 */
const props = defineProps<{ topic: string }>()
const { locale, t } = useI18n()

const show = ref(false)

const section = computed<HelpSection>(() => {
  const lang = locale.value === 'en' ? helpContent.en : helpContent.zh
  return lang[props.topic] ?? lang.default
})
</script>

<template>
  <span
    class="help-btn"
    role="button"
    tabindex="0"
    :aria-label="t('help.default.title')"
    @click="show = true"
    @keydown.enter="show = true"
  >?</span>

  <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="show" preset="card" :style="{ width: '560px', maxWidth: '92vw' }" :bordered="false">
    <template #header>
      <div class="help-modal-title">
        <span class="accent-bar" aria-hidden="true"></span>
        {{ section.title }}
      </div>
    </template>
    <ol class="help-list">
      <li v-for="(line, i) in section.lines" :key="i">{{ line }}</li>
    </ol>
  </n-modal>
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
  cursor: pointer;
  user-select: none;
  flex: none;
  transition: background-color 0.15s, color 0.15s;
}
.help-btn:hover,
.help-btn:focus-visible {
  background: #0b63ce;
  color: #fff;
  outline: none;
}

/* 弹窗标题栏：左边框强调（Artemis Instructions 风格） */
.help-modal-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: #1f2329;
}
.accent-bar {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: #0b63ce;
  flex: none;
}

/* 逐条编号说明：圆形数字 + 舒适行距 */
.help-list {
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: help-line;
}
.help-list li {
  counter-increment: help-line;
  position: relative;
  padding-left: 32px;
  margin-bottom: 12px;
  font-size: 13.5px;
  line-height: 1.7;
  color: #333;
}
.help-list li:last-child {
  margin-bottom: 0;
}
.help-list li::before {
  content: counter(help-line);
  position: absolute;
  left: 0;
  top: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e8f1fb;
  color: #0b63ce;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
