<script setup lang="ts">
import { EditorView, basicSetup } from 'codemirror'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { linter } from '@codemirror/lint'
import { oneDark } from '@codemirror/theme-one-dark'
import { inject, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
const props = withDefaults(
  defineProps<{
    modelValue: string
    height?: string
    /** 只读态（详情查看）：禁编辑、去 linter */
    readonly?: boolean
  }>(),
  { readonly: false },
)
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const opsDark = inject<{ isDark: Ref<boolean> }>('opsDark')!

const el = ref<HTMLDivElement>()
let view: EditorView | null = null
let silent = false // 内部更新（外部 value 注入）时不回发

/** 亮色内联主题改用 token 色；暗色走 one-dark（ui-upgrade-design.md §6.1） */
const lightTheme = EditorView.theme({
  '&': { fontSize: '13px', background: 'var(--ops-surface)' },
  '.cm-gutters': { background: 'var(--ops-surface-2)', border: 'none' },
  '.cm-activeLine': { background: 'rgba(37, 99, 235, 0.05)' },
})

function buildExtensions() {
  return [
    basicSetup,
    json(),
    ...(props.readonly
      ? [EditorView.editable.of(false)]
      : [linter(jsonParseLinter())]),
    ...(opsDark.isDark.value ? [oneDark] : [lightTheme]),
  ]
}

function createView() {
  view = new EditorView({
    doc: props.modelValue,
    extensions: [
      ...buildExtensions(),
      EditorView.updateListener.of((u) => {
        if (u.docChanged && !silent) {
          emit('update:modelValue', u.state.doc.toString())
        }
      }),
    ],
    parent: el.value!,
  })
}

onMounted(createView)

// 外部值变化（切换 key / 格式化）时整篇替换，保持光标在开头
watch(() => props.modelValue, (v) => {
  if (!view) return
  const current = view.state.doc.toString()
  if (v !== current) {
    silent = true
    view.dispatch({ changes: { from: 0, to: current.length, insert: v } })
    silent = false
  }
})

// 暗色切换重建（Compartment 换主题可行，但重建代码更少且编辑器重建开销可忽略）
watch(() => opsDark.isDark.value, () => {
  view?.destroy()
  createView()
})

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div ref="el" class="code-editor" :style="{ height: height ?? '420px' }" />
</template>

<style scoped>
.code-editor {
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  overflow: hidden;
}
.code-editor :deep(.cm-editor) {
  height: 100%;
}
.code-editor :deep(.cm-scroller) {
  overflow: auto;
}
</style>
