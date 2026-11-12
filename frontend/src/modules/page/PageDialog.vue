<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { message } from '@/lib/message'
import { pageApi, derivePageKind, type PageResource } from './api'

const props = defineProps<{ show: boolean; siteId: string; editing: PageResource | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
type Kind = 'url' | 'html'
const kind = ref<Kind>('url')
const form = ref({ name: '', description: '', url: '', html: '' })
const saving = ref(false)
const dragOver = ref(false)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

watch(
  () => [props.show, props.editing] as const,
  ([show, item]) => {
    if (!show) return
    kind.value = (item ? derivePageKind(item) : null) ?? 'url'
    form.value = {
      name: item?.name ?? '', description: item?.description ?? '',
      url: item?.url ?? '', html: item?.html ?? '',
    }
    file.value = null
    dragOver.value = false
    if (fileInput.value) fileInput.value.value = ''
  },
  { immediate: true },
)

// 切走时清掉 HTML 内容与已选文件，避免下次切回/重开时残留
watch(kind, (v) => {
  if (v !== 'html') {
    form.value.html = ''
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
  }
})

const KINDS: Array<{ key: Kind; label: string }> = [
  { key: 'url', label: 'page.typeUrl' },
  { key: 'html', label: 'page.typeHtml' },
]

/** .htm / .html 单文件上传：读文本进 form.html；非 html 一律拒（扩展名 + MIME 双判）。 */
async function acceptFile(raw: File) {
  const name = raw.name.toLowerCase()
  if (!name.endsWith('.htm') && !name.endsWith('.html') && raw.type !== 'text/html') {
    message.error(t('page.htmlInvalid'))
    return
  }
  try {
    form.value.html = await raw.text()
    file.value = raw
    if (!props.editing || !form.value.name) {
      form.value.name = raw.name.replace(/\.[^.]+$/, '')
    }
    message.success(t('page.htmlLoaded'))
  } catch (err) {
    message.error((err as Error).message)
  }
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = '' // 同一文件可重复选择
  if (f) void acceptFile(f)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) void acceptFile(f)
}

function clearFile() {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
  if (!props.editing) form.value.html = ''
}

async function save() {
  const name = form.value.name.trim()
  if (!name) {
    message.error(t('page.needName'))
    return
  }
  // 二选一：只写所选类型的字段，其余空串（后端 PageConfig url/html 二选一）
  const data = {
    name,
    description: form.value.description.trim(),
    url: kind.value === 'url' ? form.value.url.trim() : '',
    html: kind.value === 'html' ? form.value.html : '',
  }
  if (!data.url && !data.html) {
    message.error(t('page.needOne'))
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      await pageApi.update(props.siteId, props.editing.id, data)
    } else {
      await pageApi.create(props.siteId, data)
    }
    message.success(t('page.saved'))
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
        <DialogTitle>{{ props.editing ? $t('page.edit') : $t('page.new') }}</DialogTitle>
      </DialogHeader>

      <div class="grid gap-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('page.siteLabel') }}</label>
          <!-- 站点自动匹配当前 site，只读 -->
          <Input :model-value="props.siteId" disabled />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('page.nameLabel') }} <span class="text-destructive">*</span></label>
          <Input v-model="form.name" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-start gap-3">
          <label class="pt-2 text-xs text-muted-foreground">{{ $t('page.descLabel') }}</label>
          <Input v-model="form.description" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('page.typeLabel') }}</label>
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
          <Input v-model="form.url" :placeholder="$t('page.urlPh')" />
        </div>

        <template v-else>
          <div class="flex items-center gap-2">
            <label class="text-xs text-muted-foreground">{{ $t('page.htmlLabel') }}</label>
            <span class="text-xs text-muted-foreground">{{ $t('page.htmlHint') }}</span>
          </div>
          <div
            class="file-drop"
            :class="{ over: dragOver, picked: !!file }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <template v-if="file">
              <Upload class="size-4 shrink-0" />
              <span class="min-w-0 flex-1 truncate text-sm">{{ file.name }}</span>
              <button type="button" class="shrink-0 rounded p-1 hover:bg-accent" @click="clearFile">
                <X class="size-3.5" />
              </button>
            </template>
            <template v-else>
              <Upload class="size-4 shrink-0" />
              <label class="cursor-pointer text-sm text-primary hover:underline">
                {{ $t('page.pickFile') }}
                <input ref="fileInput" type="file" accept=".htm,.html" class="hidden" @change="onPick">
              </label>
              <span class="text-xs text-muted-foreground">{{ $t('page.dropHere') }}</span>
            </template>
          </div>
          <p v-if="!file && form.html" class="text-xs text-muted-foreground">
            {{ $t('page.currentHtml', { size: form.html.length }) }}
          </p>
        </template>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button size="sm" :disabled="saving" @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.file-drop {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 1px dashed color-mix(in srgb, var(--primary) 45%, transparent);
  border-radius: var(--ops-radius-m);
  background: color-mix(in srgb, var(--primary) 5%, transparent);
  color: var(--ops-text-2);
  transition: border-color 120ms ease, background 120ms ease;
}
.file-drop.over {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 12%, transparent);
}
.file-drop.picked {
  border-style: solid;
}
</style>
