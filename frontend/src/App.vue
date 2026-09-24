<script setup lang="ts">
import { NConfigProvider, NMessageProvider, dateEnUS, dateZhCN, enUS, zhCN } from 'naive-ui'
import { naiveDateLocale, naiveLocale } from './i18n'
import MainLayout from './layouts/MainLayout.vue'
</script>

<template>
  <n-config-provider :locale="naiveLocale === 'zh-CN' ? zhCN : enUS" :date-locale="naiveDateLocale === 'zh-CN' ? dateZhCN : dateEnUS">
    <n-message-provider>
      <MainLayout />
    </n-message-provider>
  </n-config-provider>
</template>
