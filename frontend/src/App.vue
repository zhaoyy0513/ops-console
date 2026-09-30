<script setup lang="ts">
import { computed, provide } from 'vue'
import { useDark, useToggle } from '@vueuse/core'
import {
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  dateEnUS,
  dateZhCN,
  darkTheme,
  enUS,
  zhCN,
  type GlobalThemeOverrides,
} from 'naive-ui'
import { naiveDateLocale, naiveLocale } from './i18n'
import MainLayout from './layouts/MainLayout.vue'

const isDark = useDark()
const toggleDark = useToggle(isDark)
// 供 MainLayout 顶栏按钮使用（provide 避免再引一次 useDark）；isDark 本身随系统偏好自动响应
provide('opsDark', { isDark, toggle: toggleDark })

/** 令牌同源的主题覆盖（§3.2：色值来自 tokens.css 的同一组常量） */
const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: '#2563eb',
    primaryColorHover: '#3b82f6',
    primaryColorPressed: '#1d4ed8',
    borderRadius: '4px',
    fontFamily: " 'Inter Variable', system-ui, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    ...(isDark.value
      ? { bodyColor: '#101014', cardColor: '#17171c', modalColor: '#17171c', popoverColor: '#202026' }
      : {}),
  },
}))
</script>

<template>
  <n-config-provider
    :theme="isDark ? darkTheme : undefined"
    :theme-overrides="themeOverrides"
    :locale="naiveLocale === 'zh-CN' ? zhCN : enUS"
    :date-locale="naiveDateLocale === 'zh-CN' ? dateZhCN : dateEnUS"
  >
    <n-loading-bar-provider>
      <n-dialog-provider>
        <n-message-provider>
          <MainLayout />
        </n-message-provider>
      </n-dialog-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
