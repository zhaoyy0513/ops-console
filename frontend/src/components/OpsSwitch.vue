<script setup lang="ts">
/** 业务开关：v-model:value / disabled / size（沿用旧 API，消费方不动）。
 *  未传 value（undefined）视为关——行内绑定的后端字段多为 optional。
 *  size 仅作兼容保留（shadcn Switch 单尺寸，视觉差异交给主题 token）。 */
import { computed } from 'vue'
import { Switch } from '@/components/ui/switch'

const props = defineProps<{ value?: boolean; disabled?: boolean; size?: 'small' | 'medium' }>()
const emit = defineEmits<{ (e: 'update:value', v: boolean): void }>()

const checked = computed({
  get: () => !!props.value,
  set: (v: boolean) => emit('update:value', v),
})
</script>

<template>
  <Switch v-model="checked" :disabled="disabled" />
</template>
