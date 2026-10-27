<script setup lang="ts">
import { computed, provide, watchEffect } from 'vue'
import { Toaster } from 'vue-sonner'
import { TooltipProvider } from 'reka-ui'
import { useThemeStore } from './stores/theme'
import MainLayout from './layouts/MainLayout.vue'

// 画风状态唯一事实来源是 theme store；此处只负责把它投影到 <html data-theme>。
// 组件（图表/编辑器）通过 inject('opsTheme') 拿到主题名做自己的深浅判断。
const theme = useThemeStore()

watchEffect(() => {
  document.documentElement.dataset.theme = theme.theme
})

provide('opsTheme', computed(() => theme.theme))
</script>

<template>
  <!-- 全站唯一 TooltipProvider：reka 的 Tooltip 注入缺 Provider 会抛错并损坏组件树
      （表现为 patch 阶段 emitsOptions/parentNode null 崩溃），在此统一提供 -->
  <TooltipProvider :delay-duration="100">
    <MainLayout />
    <Toaster :theme="theme.theme === 'light' ? 'light' : 'dark'" position="top-center" rich-colors close-button />
  </TooltipProvider>
</template>
