<script setup lang="ts">
import { NConfigProvider, NMessageProvider, dateZhCN, zhCN } from 'naive-ui'
import MainLayout from './layouts/MainLayout.vue'
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <MainLayout />
    </n-message-provider>
  </n-config-provider>
</template>
