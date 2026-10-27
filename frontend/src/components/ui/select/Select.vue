<script setup lang="ts">
import { SelectRoot } from 'reka-ui'
import { ref, watchEffect } from 'vue'

// modelValue 显式转发；open 内部自治（reka 受控 open 需要外部监听回写，
// 包装层不监听会导致弹层无法打开）
const props = defineProps<{ modelValue?: string | null; open?: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const open = ref(false)
watchEffect(() => {
  if (props.open !== undefined) open.value = props.open
})
</script>

<template>
  <SelectRoot
    :model-value="props.modelValue"
    v-model:open="open"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <slot />
  </SelectRoot>
</template>
