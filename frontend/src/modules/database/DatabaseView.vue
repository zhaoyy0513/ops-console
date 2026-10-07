<script setup lang="ts">
import { NCard } from 'naive-ui'
import EmptyState from '../../components/EmptyState.vue'
</script>

<template>
  <n-card :title="$t('database.title')" size="small">
    <EmptyState :title="$t('database.line2')" />
  </n-card>
</template>
