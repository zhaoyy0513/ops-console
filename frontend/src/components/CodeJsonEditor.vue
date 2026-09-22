<script setup lang="ts">
import { EditorView, basicSetup } from 'codemirror'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { linter } from '@codemirror/lint'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  height?: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const el = ref<HTMLDivElement>()
let view: EditorView | null = null
let silent = false // 内部更新（外部 value 注入）时不回发

onMounted(() => {
  view = new EditorView({
    doc: props.modelValue,
    extensions: [
      basicSetup,
      json(),
      linter(jsonParseLinter()),
      EditorView.updateListener.of((u) => {
        if (u.docChanged && !silent) {
          emit('update:modelValue', u.state.doc.toString())
        }
      }),
      EditorView.theme({
        '&': { fontSize: '13px', background: '#fafbfc' },
        '.cm-gutters': { background: '#f0f1f3', border: 'none' },
        '.cm-activeLine': { background: 'rgba(11,99,206,0.04)' },
      }),
    ],
    parent: el.value!,
  })
})

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

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div ref="el" class="code-editor" :style="{ height: height ?? '420px' }" />
</template>

<style scoped>
.code-editor {
  border: 1px solid #e5e6eb;
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
