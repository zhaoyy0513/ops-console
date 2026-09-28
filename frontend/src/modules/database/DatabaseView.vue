<script setup lang="ts">
import { NCard } from 'naive-ui'
</script>

<template>
  <n-card :title="$t('database.title')" size="small">
    <p>{{ $t('database.line1') }}</p>
    <p>{{ $t('database.line2') }}</p>
  </n-card>
</template>
