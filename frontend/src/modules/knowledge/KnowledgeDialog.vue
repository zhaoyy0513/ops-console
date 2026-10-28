<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileUp, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { message } from '@/lib/message'
import { humanSize, knowledgeApi, validateUpload, type KnowledgeDoc } from './api'

const props = defineProps<{
  show: boolean
  siteId: string
  /** 站点显示名（弹窗里展示名称而非 id） */
  siteName: string
  editing: KnowledgeDoc | null
  /** 拖拽预填：视图 dropzone 已接住的文件 */
  prefillFile?: File | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
const file = ref<File | null>(null)
const name = ref('')
const description = ref('')
const saving = ref(false)
const dragOver = ref(false)

const isRename = computed(() => !!props.editing)

watch(
  () => [props.show, props.editing, props.prefillFile] as const,
  ([show, item, prefill]) => {
    if (!show) return
    file.value = null
    dragOver.value = false
    if (item) {
      name.value = item.name
      description.value = item.description ?? ''
      return
    }
    name.value = ''
    description.value = ''
    if (prefill) acceptFile(prefill)
  },
  { immediate: true },
)

/** 选中/拖入文件：校验大小与空文件，名称默认取文件名去扩展名 */
function acceptFile(f: File) {
  const err = validateUpload(f)
  if (err) {
    message.error(t(err, { max: humanSize(1_000_000) }))
    return
  }
  file.value = f
  if (!name.value.trim()) name.value = f.name.replace(/\.[^.]+$/, '')
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = '' // 同一文件可重复选择
  if (f) acceptFile(f)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) acceptFile(f)
}

async function save() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    message.error(t('knowledge.needName'))
    return
  }
  saving.value = true
  try {
    if (props.editing) {
      // 内容创建后不可变：仅改名/描述
      await knowledgeApi.update(props.siteId, props.editing.id, {
        name: trimmed,
        description: description.value.trim(),
      })
    } else {
      if (!file.value) {
        message.error(t('knowledge.needFile'))
        saving.value = false
        return
      }
      await knowledgeApi.create(props.siteId, file.value, trimmed, description.value.trim())
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
        <DialogTitle>{{ isRename ? $t('knowledge.rename') : $t('knowledge.new') }}</DialogTitle>
      </DialogHeader>

      <div class="grid gap-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.siteLabel') }}</label>
          <!-- 显示站点名称（不是内部 id） -->
          <Input :model-value="props.siteName || props.siteId" disabled />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.nameLabel') }} <span class="text-destructive">*</span></label>
          <Input v-model="name" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.descLabel') }}</label>
          <Input v-model="description" />
        </div>

        <!-- 编辑态：内容不可变，只提示 -->
        <div v-if="isRename" class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          {{ $t('knowledge.renameOnly') }}
        </div>

        <!-- 新建态：任意格式文件（点击选择或拖入） -->
        <template v-else>
          <div
            class="file-drop"
            :class="{ over: dragOver, picked: !!file }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <template v-if="file">
              <FileUp class="size-5 shrink-0" />
              <span class="min-w-0 flex-1 truncate text-sm">{{ file.name }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ humanSize(file.size) }}</span>
              <button type="button" class="shrink-0 rounded p-1 hover:bg-accent" @click="file = null">
                <X class="size-3.5" />
              </button>
            </template>
            <template v-else>
              <FileUp class="size-5 shrink-0" />
              <label class="cursor-pointer text-sm text-primary hover:underline">
                {{ $t('knowledge.pickFile') }}
                <input type="file" class="hidden" @change="onPick">
              </label>
              <span class="text-xs text-muted-foreground">{{ $t('knowledge.dropHere') }}</span>
            </template>
          </div>
          <p class="text-xs text-muted-foreground">{{ $t('knowledge.anyFormatHint', { max: humanSize(1_000_000) }) }}</p>
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
