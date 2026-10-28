<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Upload } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import { pageApi, derivePageKind, type PageResource } from './api'

const props = defineProps<{ show: boolean; siteId: string; editing: PageResource | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
type Kind = 'url' | 'html'
const kind = ref<Kind>('url')
const form = ref({ name: '', description: '', url: '', html: '' })
const saving = ref(false)

watch(
  () => [props.show, props.editing] as const,
  ([show, item]) => {
    if (!show) return
    kind.value = (item ? derivePageKind(item) : null) ?? 'url'
    form.value = {
      name: item?.name ?? '', description: item?.description ?? '',
      url: item?.url ?? '', html: item?.html ?? '',
    }
  },
  { immediate: true },
)

const KINDS: Array<{ key: Kind; label: string }> = [
  { key: 'url', label: 'page.typeUrl' },
  { key: 'html', label: 'page.typeHtml' },
]

/** .html 单文件上传：读文本进 form.html；非 .html 一律拒（扩展名 + MIME 双判）。
 *  原生 file input：选中即读内容并清空选择，可重复选同一文件。 */
async function onHtmlFile(e: Event) {
  const input = e.target as HTMLInputElement
  const raw = input.files?.[0]
  input.value = '' // 先清空，同一文件可再次选择覆盖
  if (!raw) return
  const name = raw.name.toLowerCase()
  if (!name.endsWith('.html') && raw.type !== 'text/html') {
    message.error(t('page.htmlInvalid'))
    return
  }
  try {
    form.value.html = await raw.text()
    message.success(t('page.htmlLoaded'))
  } catch (err) {
    message.error((err as Error).message)
  }
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
            <label class="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline">
              <Upload class="size-3.5" />
              {{ $t('page.uploadHtml') }}
              <input type="file" accept=".html" class="hidden" @change="onHtmlFile">
            </label>
          </div>
          <Textarea
            v-model="form.html"
            class="min-h-[220px] font-mono text-[13px]"
            :placeholder="$t('page.htmlPh')"
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
