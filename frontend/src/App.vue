<script setup lang="ts">
import { computed, provide } from 'vue'
import { useDark } from '@vueuse/core'
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

// useDark() 返回 WritableComputedRef<boolean>（getter 读 state、setter 写 store）。
// 直接 isDark.value = !isDark.value 走 setter → 写底层 store → 切换生效。
// 不用 useToggle（它内部也是同样赋值，但多一层间接）也不用 useColorMode 的
// 内部 store/state 解构（版本差异可能导致 store 为 undefined → 白屏）。
const isDark = useDark()
const toggleDark = () => { isDark.value = !isDark.value }
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
