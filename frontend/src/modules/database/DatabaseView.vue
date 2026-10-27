<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '../../components/EmptyState.vue'
</script>

<template>
  <Card>
    <CardHeader><CardTitle>{{ $t('database.title') }}</CardTitle></CardHeader>
    <CardContent><EmptyState :title="$t('database.line2')" /></CardContent>
  </Card>
</template>
