<script setup lang="ts">
import { NCard } from 'naive-ui'
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <n-card title="Demo 模块" size="small">
    <p>siteId: {{ route.params.siteId }}</p>
    <p>本页面由模块注册机制自动挂载，未改动任何核心框架代码。</p>
  </n-card>
</template>
