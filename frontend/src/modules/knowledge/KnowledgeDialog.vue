<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import { knowledgeApi, deriveKind, type KnowledgeResource } from './api'

const props = defineProps<{ show: boolean; siteId: string; editing: KnowledgeResource | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
type Kind = 'url' | 'markdown' | 'html'
const kind = ref<Kind>('url')
const form = ref({ name: '', description: '', url: '', markdown: '', html: '' })
const saving = ref(false)

watch(
  () => [props.show, props.editing] as const,
  ([show, item]) => {
    if (!show) return
    kind.value = (item ? deriveKind(item) : null) ?? 'url'
    form.value = {
      name: item?.name ?? '', description: item?.description ?? '',
      url: item?.url ?? '', markdown: item?.markdown ?? '', html: item?.html ?? '',
    }
  },
  { immediate: true },
)

const KINDS: Array<{ key: Kind; label: string }> = [
  { key: 'url', label: 'knowledge.typeUrl' },
  { key: 'markdown', label: 'knowledge.typeMarkdown' },
  { key: 'html', label: 'knowledge.typeHtml' },
]

/** .md 单文件上传：读文本进 form.markdown（扩展名 + MIME 双判，同 .html 上传惯例） */
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
    message.success(t('knowledge.mdLoaded'))
  } catch (err) {
    message.error((err as Error).message)
  }
}

/** 粘贴图片 → canvas 压缩（1280px / JPEG 0.8）→ base64 data URI 插入光标处。
 *  非图片粘贴走默认行为；压缩失败静默忽略不阻塞输入。 */
async function onMarkdownPaste(e: ClipboardEvent) {
  const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith('image/'))
  if (!item) return
  const file = item.getAsFile()
  if (!file) return
  e.preventDefault()
  // 直接用事件目标元素定位光标（Textarea 是包装组件，模板 ref 拿不到原生元素）
  const el = e.target as HTMLTextAreaElement | null
  // await 前同步快照光标：压缩的异步间隙里 DOM 选区可能已被下一次输入/粘贴改变
  const s = el?.selectionStart
  const end = el?.selectionEnd
  try {
    insertAtCursor(el, s, end, `![](${await compressImage(file)})`)
    message.success(t('knowledge.imgInserted'))
  } catch { /* 压缩失败忽略，不阻塞输入 */ }
}

async function compressImage(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, 1280 / bitmap.width)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#fff' // 透明 PNG 压 JPEG 会变黑底，先铺白
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', 0.8)
  } finally {
    bitmap.close()
  }
}

function insertAtCursor(el: HTMLTextAreaElement | null, s: number | undefined, end: number | undefined, text: string) {
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
  // 只写所选类型字段，其余置空串（后端空白视同未填；编辑切换类型不残留旧内容）
  const data = {
    name,
    description: form.value.description.trim(),
    url: kind.value === 'url' ? form.value.url.trim() : '',
    markdown: kind.value === 'markdown' ? form.value.markdown : '',
    html: kind.value === 'html' ? form.value.html : '',
  }
  if (!data.url && !data.markdown && !data.html) {
    message.error(t('knowledge.needOne'))
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      await knowledgeApi.update(props.siteId, props.editing.id, data)
    } else {
      await knowledgeApi.create(props.siteId, data)
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
        <DialogTitle>{{ props.editing ? $t('knowledge.edit') : $t('knowledge.new') }}</DialogTitle>
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
        <div class="grid grid-cols-[90px_1fr] items-start gap-3">
          <label class="pt-2 text-xs text-muted-foreground">{{ $t('knowledge.descLabel') }}</label>
          <Input v-model="form.description" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.typeLabel') }}</label>
          <div class="flex gap-1.5">
            <Button
              v-for="k in KINDS" :key="k.key"
              :variant="kind === k.key ? 'default' : 'outline'" size="sm"
              @click="kind = k.key"
            >
              {{ $t(k.label) }}
            </Button>
          </div>
        </div>

        <div v-if="kind === 'url'" class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">URL</label>
          <Input v-model="form.url" placeholder="https://" />
        </div>

        <template v-else-if="kind === 'markdown'">
          <div class="flex items-center gap-2">
            <label class="text-xs text-muted-foreground">Markdown</label>
            <label class="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline">
              <Upload class="size-3.5" />
              {{ $t('knowledge.uploadMd') }}
              <input type="file" accept=".md,.markdown,text/markdown" class="hidden" @change="onMdFile">
            </label>
          </div>
          <Textarea
            v-model="form.markdown"
            class="min-h-[220px] font-mono text-[13px]"
            :placeholder="$t('knowledge.mdPh')"
            @paste="onMarkdownPaste"
          />
        </template>

        <template v-else>
          <div class="grid grid-cols-[90px_1fr] items-start gap-3">
            <label class="pt-2 text-xs text-muted-foreground">HTML</label>
            <Textarea v-model="form.html" class="min-h-[180px] font-mono text-[13px]" :placeholder="$t('knowledge.htmlPh')" />
          </div>
        </template>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button size="sm" :disabled="saving" @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
