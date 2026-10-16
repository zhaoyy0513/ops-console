<script setup lang="ts">
import { computed, provide } from 'vue'
import { useColorMode } from '@vueuse/core'
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

// 主题：useDark() 返回的是 useColorMode 的 state（computed），"auto" 时它跟随
// 操作系统；useToggle(state) 的写回打在 computed 上会静默失败（Vue 对只读
// computed 赋值不报错）——这就是"切一次没反应、再点又动了"的原因。
// 正确做法：切换写 store（可写 ref），display 读 state。
// storageKey 沿用默认的 vueuse-color-scheme：老用户的旧选择不会丢。
const mode = useColorMode({ disableTransition: true })
const { store, state: isDark } = mode
// 写 store（可写），不写 state（computed，赋值静默失败）
const toggleDark = () => { store.value = isDark.value ? 'light' : 'dark' }
// 供 MainLayout 顶栏按钮使用；isDark 随 store / 系统偏好自动响应
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
