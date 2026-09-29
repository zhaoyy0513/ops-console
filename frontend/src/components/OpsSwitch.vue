<script setup lang="ts">
/** SquishSwitch 的业务封装：API 对齐 NSwitch（v-model:value / disabled / size，
 *  value 允许 undefined——行内绑定的后端字段多为 optional）。 */
import SquishSwitch from './bits/SquishSwitch.vue'

defineProps<{ value?: boolean; disabled?: boolean; size?: 'small' | 'medium' }>()
const emit = defineEmits<{ (e: 'update:value', v: boolean): void }>()
</script>

<template>
  <SquishSwitch
    :value="!!value"
    :disabled="disabled"
    :size="size"
    @update:value="emit('update:value', $event)"
  />
</template>
