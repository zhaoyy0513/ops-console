<script setup lang="ts">
// 可排序表头单元格（手写 n-table 用）：标签 + 上下小箭头（未激活弱化，激活主色）。
// 整个 th 可点击；style/class 经 attrs 透传到根 th，与原列宽写法兼容（style="width: 90px"）。
defineProps<{
  label: string
  active?: boolean
  dir?: 'asc' | 'desc' | null
}>()
const emit = defineEmits<{ (e: 'sort'): void }>()
</script>

<template>
  <th class="sort-th" :class="{ active }" @click="emit('sort')">
    <span class="sort-label">{{ label }}</span>
    <span class="sort-arrows" aria-hidden="true">
      <span class="arr" :class="{ on: active && dir === 'asc' }">▲</span>
      <span class="arr" :class="{ on: active && dir === 'desc' }">▼</span>
    </span>
  </th>
</template>

<style scoped>
.sort-th {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.sort-label {
  vertical-align: middle;
}
.sort-arrows {
  display: inline-flex;
  flex-direction: column;
  vertical-align: middle;
  margin-left: 4px;
  line-height: 1;
}
.arr {
  font-size: 8px;
  line-height: 6px;
  color: var(--ops-text-3);
  opacity: 0.45;
}
.arr.on {
  color: var(--ops-primary);
  opacity: 1;
}
</style>
