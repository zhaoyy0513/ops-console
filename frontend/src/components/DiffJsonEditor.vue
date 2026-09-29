<script setup lang="ts">
import { EditorView, basicSetup } from 'codemirror'
import { json } from '@codemirror/lang-json'
import { oneDark } from '@codemirror/theme-one-dark'
import { MergeView } from '@codemirror/merge'
import { inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

// git-review 式左右对比：左 = Redis 当前值（只读），右 = 编辑侧（v-model），
// 变更块红/绿高亮由 @codemirror/merge 自带主题渲染
const props = withDefaults(
  defineProps<{
    original: string
    modelValue: string
    height?: string
  }>(),
  { height: '420px' },
)
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const opsDark = inject<{ isDark: Ref<boolean> }>('opsDark')!

const el = ref<HTMLDivElement>()
let view: MergeView | null = null
let silent = false // 内部更新（外部 value 注入）时不回发

const lightTheme = EditorView.theme({
  '&': { fontSize: '13px', background: 'var(--ops-surface)' },
  '.cm-gutters': { background: 'var(--ops-surface-2)', border: 'none' },
  '.cm-activeLine': { background: 'rgba(37, 99, 235, 0.05)' },
})

function theme() {
  return opsDark.isDark.value ? [oneDark] : [lightTheme]
}

function createView() {
  view = new MergeView({
    a: {
      doc: props.original,
      extensions: [basicSetup, json(), EditorView.editable.of(false), ...theme()],
    },
    b: {
      doc: props.modelValue,
      extensions: [
        basicSetup,
        json(),
        ...theme(),
        EditorView.updateListener.of((u) => {
          if (u.docChanged && !silent) emit('update:modelValue', u.state.doc.toString())
        }),
      ],
    },
    parent: el.value!,
  })
}

onMounted(createView)

// original 变化 = 切换了 key，整体重建（diff 基线不同）
watch(() => props.original, () => {
  view?.destroy()
  createView()
})

// 外部改编辑值（罕见）：整篇替换进右侧编辑器
watch(() => props.modelValue, (v) => {
  if (!view) return
  const current = view.b.state.doc.toString()
  if (v !== current) {
    silent = true
    view.b.dispatch({ changes: { from: 0, to: current.length, insert: v } })
    silent = false
  }
})

// 暗色切换重建（同 CodeJsonEditor：重建比 Compartment 少代码）
watch(() => opsDark.isDark.value, () => {
  view?.destroy()
  createView()
})

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div ref="el" class="diff-editor" :style="{ height }" />
</template>

<style scoped>
.diff-editor {
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  overflow: hidden;
}
/* merge 包约定：容器给高度+滚动，两侧编辑器自然高度随容器整体滚动 */
.diff-editor :deep(.cm-mergeView) {
  height: 100%;
  overflow: auto;
}
</style>
