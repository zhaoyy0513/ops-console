<script setup lang="ts">
import { EditorView, basicSetup } from 'codemirror'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { linter } from '@codemirror/lint'
import { oneDark } from '@codemirror/theme-one-dark'
import { MergeView } from '@codemirror/merge'
import { computed, inject, onBeforeUnmount, onMounted, ref, watch, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'

// git-review 式左右对比：左 = Redis 当前值（只读），右 = 编辑侧（v-model），
// 变更行红/绿整行底色由下方 scoped 样式强化（merge 包默认底色过淡）
const props = withDefaults(
  defineProps<{
    original: string
    modelValue: string
    height?: string
  }>(),
  { height: '420px' },
)
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const { t } = useI18n()
// 三态画风；编辑器只有亮/暗两套主题，mono/terminal 归暗
const theme = inject<ComputedRef<'light' | 'dark'>>('opsTheme', computed(() => 'light'))

const el = ref<HTMLDivElement>()
let view: MergeView | null = null
let silent = false // 内部更新（外部 value 注入）时不回发

const lightTheme = EditorView.theme({
  '&': { fontSize: '13px', background: 'var(--ops-surface)' },
  '.cm-gutters': { background: 'var(--ops-surface-2)', border: 'none' },
  '.cm-activeLine': { background: 'rgba(37, 99, 235, 0.05)' },
})

function themeExts() {
  return theme.value === 'light' ? [lightTheme] : [oneDark]
}

function createView() {
  view = new MergeView({
    a: {
      doc: props.original,
      extensions: [basicSetup, json(), EditorView.editable.of(false), ...themeExts()],
    },
    b: {
      doc: props.modelValue,
      extensions: [
        basicSetup,
        json(),
        // 行内红波浪线实时标出语法错误（行/列详情由外层横幅展示）
        linter(jsonParseLinter()),
        ...themeExts(),
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

// 画风切换重建（同 CodeJsonEditor：重建比 Compartment 少代码；
// watch 映射后的主题名，mono/terminal 同为暗不重复重建）
watch(() => (theme.value === 'light' ? 'light' : 'dark'), () => {
  view?.destroy()
  createView()
})

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div class="diff-wrap" :style="{ height }">
    <!-- 双侧标签行：左=原始只读，右=可编辑（用户反馈：看不出哪侧能改） -->
    <div class="diff-headers">
      <span class="side-label">{{ t('redis.diffOriginal') }}</span>
      <span class="side-label edited">{{ t('redis.diffEdited') }}</span>
    </div>
    <div ref="el" class="diff-editor" />
  </div>
</template>

<style scoped>
.diff-wrap {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  overflow: hidden;
  /* 防止在 flex 行内被内容（merge 双栏）撑出最小宽度，页面级横向滚动的根源之一 */
  min-width: 0;
}
.diff-headers {
  display: flex;
  flex: none;
  border-bottom: 1px solid var(--ops-border);
}
.side-label {
  flex: 1;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--ops-text-3);
  background: var(--ops-surface-2);
  white-space: nowrap;
  overflow: hidden;
}
.side-label + .side-label {
  border-left: 1px solid var(--ops-border);
}
.side-label.edited {
  color: var(--ops-primary);
  font-weight: 600;
}
.diff-editor {
  flex: 1;
  min-height: 0;
  min-width: 0;
}
/* merge 包约定：容器给高度+滚动，两侧编辑器自然高度随容器整体滚动 */
.diff-editor :deep(.cm-mergeView) {
  height: 100%;
  overflow: auto;
}
/* JSON 语法错误标记增强：CM 默认只是行内两个小圆点（cm-lintRange-error 的
   默认背景图），肉眼几乎不可见——覆盖为浅红底色 + 醒目的红色波浪下划线。
   （类名核实于 @codemirror/lint 6.9.7 dist：mark decoration 挂 cm-lintRange-error）
   悬浮仍有 lint tooltip 显示完整错误信息。 */
.diff-editor :deep(.cm-lintRange-error) {
  background-image: none;
  background-color: rgba(208, 48, 80, 0.12);
  text-decoration: underline wavy #d03050 2px;
  text-decoration-skip-ink: none;
  text-underline-offset: 3px;
}
/* 变更行整行底色 + 左侧 2px 实色条（用户反馈：默认底色太淡，变更行不醒目）。
   merge 包在两侧 .cm-editor 上分别标 cm-merge-a / cm-merge-b，变更行加 .cm-changedLine；
   a 侧=删除（红）b 侧=新增（绿），同 git-review 语义。
   用 inset 阴影做色条而非 border：不占布局，两侧编辑器行不错位。
   半透明色亮/暗两种主题下均可读，无需分主题覆盖 */
.diff-editor :deep(.cm-merge-a .cm-changedLine) {
  background: rgba(208, 48, 80, 0.14);
  box-shadow: inset 2px 0 0 #d03050;
}
.diff-editor :deep(.cm-merge-b .cm-changedLine) {
  background: rgba(39, 174, 96, 0.16);
  box-shadow: inset 2px 0 0 #27ae60;
}
/* 行内变更文字再加深一档，精确定位到 token（cm-deletedLine 在 a 侧、cm-insertedLine 在 b 侧） */
.diff-editor :deep(.cm-merge-a .cm-changedLine .cm-deletedLine) {
  background: rgba(208, 48, 80, 0.18);
}
.diff-editor :deep(.cm-merge-b .cm-changedLine .cm-insertedLine) {
  background: rgba(39, 174, 96, 0.22);
}
</style>
