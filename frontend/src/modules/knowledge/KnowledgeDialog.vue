<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ImagePlus, Upload } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import { classifyDropFiles, compressImage, knowledgeApi, type KnowledgeDoc } from './api'

const props = defineProps<{
  show: boolean
  siteId: string
  editing: KnowledgeDoc | null
  /** 拖拽预填（仅新建用）：视图级 dropzone 解析出的名称与正文 */
  prefill?: { name?: string; markdown?: string } | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
const form = ref({ name: '', description: '', markdown: '' })
const saving = ref(false)

watch(
  () => [props.show, props.editing, props.prefill] as const,
  ([show, item, prefill]) => {
    if (!show) return
    // 编辑态仅可改名（内容创建后不可变）；新建用拖拽预填或空表单
    form.value = item
      ? { name: item.name, description: item.description ?? '', markdown: item.markdown ?? '' }
      : { name: prefill?.name ?? '', description: '', markdown: prefill?.markdown ?? '' }
  },
  { immediate: true },
)

/** .md 单文件上传：读文本进正文（扩展名 + MIME 双判） */
async function onMdFile(e: Event) {
  const input = e.target as HTMLInputElement
  const raw = input.files?.[0]
  input.value = ''
  if (!raw) return
  const name = raw.name.toLowerCase()
  if (!name.endsWith('.md') && !name.endsWith('.markdown') && raw.type !== 'text/markdown') {
    message.error(t('knowledge.mdInvalid'))
    return
  }
  try {
    form.value.markdown = await raw.text()
    if (!form.value.name) form.value.name = raw.name.replace(/\.(md|markdown)$/i, '')
    message.success(t('knowledge.mdLoaded'))
  } catch (err) {
    message.error((err as Error).message)
  }
}

/** 「上传图片」：压缩后以独立图片文档形态生成正文（![](data:…)），名称取文件名 */
async function onImageFile(e: Event) {
  const input = e.target as HTMLInputElement
  const files = [...(input.files ?? [])]
  input.value = ''
  let inserted = 0
  for (const file of files) {
    try {
      const md = `![](${await compressImage(file)})`
      form.value.markdown = form.value.markdown ? `${form.value.markdown}\n\n${md}` : md
      if (!form.value.name) form.value.name = file.name.replace(/\.[^.]+$/, '')
      inserted++
    } catch { /* 压缩失败忽略该张 */ }
  }
  if (inserted) message.success(t('knowledge.imgInserted'))
}

/** 粘贴图片 → 压缩 → 插入光标处（快照坐标在 await 前取，异步间隙不丢位）。非图片粘贴走默认行为。 */
async function onMarkdownPaste(e: ClipboardEvent) {
  const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))
  if (!item) return
  const file = item.getAsFile()
  if (!file) return
  e.preventDefault()
  // Textarea 是包装组件拿不到模板 ref，直接用事件目标元素定位光标
  const el = e.target as HTMLTextAreaElement | null
  const s = el?.selectionStart
  const end = el?.selectionEnd
  try {
    insertAt(el, s, end, `![](${await compressImage(file)})`)
    message.success(t('knowledge.imgInserted'))
  } catch { /* 压缩失败忽略，不阻塞输入 */ }
}

/** 编辑器内拖放：语义同粘贴（插入光标处）；.md 拖入则整篇替换 */
async function onMarkdownDrop(e: DragEvent) {
  const files = [...(e.dataTransfer?.files ?? [])]
  if (!files.length) return
  e.preventDefault()
  const { markdownFiles, imageFiles } = classifyDropFiles(files)
  if (markdownFiles.length) {
    try {
      form.value.markdown = await markdownFiles[0].text()
      if (!form.value.name) form.value.name = markdownFiles[0].name.replace(/\.(md|markdown)$/i, '')
      message.success(t('knowledge.mdLoaded'))
    } catch (err) {
      message.error((err as Error).message)
    }
  }
  for (const img of imageFiles) {
    const el = e.target as HTMLTextAreaElement | null
    const s = el?.selectionStart
    const end = el?.selectionEnd
    try {
      insertAt(el, s, end, `![](${await compressImage(img)})`)
      message.success(t('knowledge.imgInserted'))
    } catch { /* 忽略 */ }
  }
}

function insertAt(el: HTMLTextAreaElement | null, s: number | undefined, end: number | undefined, text: string) {
  if (!el || s === undefined) {
    form.value.markdown += text
    return
  }
  // 坐标来自 await 前的快照；切片用 form（模型值），textarea 的 DOM 值此刻可能已变
  const v = form.value.markdown
  form.value.markdown = v.slice(0, s) + text + v.slice(end ?? s)
}

async function save() {
  const name = form.value.name.trim()
  if (!name) {
    message.error(t('knowledge.needName'))
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      // 内容创建后不可变：编辑仅重命名（PUT 只带 name，后端全可选更新语义天然保内容）
      await knowledgeApi.update(props.siteId, props.editing.id, { name })
    } else {
      if (!form.value.markdown.trim()) {
        message.error(t('knowledge.needOne'))
        saving.value = false
        return
      }
      await knowledgeApi.create(props.siteId, {
        name,
        description: form.value.description.trim(),
        markdown: form.value.markdown,
      })
    }
    message.success(t('knowledge.saved'))
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="w-[560px] max-w-[92vw]" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ props.editing ? $t('knowledge.rename') : $t('knowledge.new') }}</DialogTitle>
      </DialogHeader>

      <div class="grid gap-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.siteLabel') }}</label>
          <!-- 站点自动匹配当前 site，只读 -->
          <Input :model-value="props.siteId" disabled />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.nameLabel') }} <span class="text-destructive">*</span></label>
          <Input v-model="form.name" />
        </div>

        <!-- 编辑态：仅名称（内容创建后不可变） -->
        <template v-if="props.editing">
          <div class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            {{ $t('knowledge.renameOnly') }}
          </div>
        </template>

        <template v-else>
          <div class="grid grid-cols-[90px_1fr] items-start gap-3">
            <label class="pt-2 text-xs text-muted-foreground">{{ $t('knowledge.descLabel') }}</label>
            <Input v-model="form.description" />
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <label class="text-xs text-muted-foreground">Markdown</label>
            <label class="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline">
              <Upload class="size-3.5" />
              {{ $t('knowledge.uploadMd') }}
              <input type="file" accept=".md,.markdown,text/markdown" class="hidden" @change="onMdFile">
            </label>
            <label class="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline">
              <ImagePlus class="size-3.5" />
              {{ $t('knowledge.uploadImg') }}
              <input type="file" accept="image/*" multiple class="hidden" @change="onImageFile">
            </label>
          </div>
          <Textarea
            v-model="form.markdown"
            class="min-h-[220px] font-mono text-[13px]"
            :placeholder="$t('knowledge.mdPh')"
            @paste="onMarkdownPaste"
            @drop="onMarkdownDrop"
          />
        </template>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button size="sm" :disabled="saving" @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
