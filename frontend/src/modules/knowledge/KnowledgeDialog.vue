<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
import { FileUp, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { message } from '@/lib/message'
import { humanSize, knowledgeApi, MAX_FILE_LABEL, validateUpload, type KnowledgeDoc } from './api'

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
/** 上传态：进度条 + 取消都吃这三个；total 为 0 时进度条退化为 0%（对端没给大小） */
const uploading = ref(false)
const uploaded = ref(0)
const uploadTotal = ref(0)
let uploadController: AbortController | null = null

const uploadPct = computed(() =>
  uploadTotal.value > 0 ? Math.min(100, Math.round((uploaded.value / uploadTotal.value) * 100)) : 0,
)
/** 上传中锁住表单：中途换文件/改名字会让进度与最终落盘的对象对不上 */
const locked = computed(() => uploading.value)

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

/** 选中/拖入文件：校验大小与空文件；名称始终跟随文件名（去扩展名）自动填充 */
function acceptFile(f: File) {
  const err = validateUpload(f)
  if (err) {
    message.error(t(err, { max: MAX_FILE_LABEL }))
    return
  }
  file.value = f
  name.value = f.name.replace(/\.[^.]+$/, '')
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

/** 中断上传（Cancel 按钮 / 关闭弹窗共用）。 */
function abortUpload() {
  uploadController?.abort()
  uploadController = null
}

/** 统一关闭出口：右上角 X 与 footer 取消都走这里。
    上传中关闭必须同时中断，否则请求在后台跑完——进度条已经消失，
    用户看不到它其实成功了。 */
function onOpenChange(v: boolean) {
  if (!v && uploading.value) abortUpload()
  emit('update:show', v)
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
      const f = file.value
      if (!f) {
        message.error(t('knowledge.needFile'))
        return
      }
      uploading.value = true
      uploaded.value = 0
      uploadTotal.value = f.size
      uploadController = new AbortController()
      await knowledgeApi.create(props.siteId, f, trimmed, description.value.trim(), {
        onProgress: (loaded, total) => {
          uploaded.value = loaded
          uploadTotal.value = total || f.size
        },
        signal: uploadController.signal,
      })
    }
    message.success(props.editing ? t('knowledge.saved') : t('knowledge.uploadSuccess'))
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    // 取消是用户主动动作，不是错误：给提示不给红色报错
    if (axios.isCancel(e)) message.info(t('knowledge.uploadCanceled'))
    else message.error((e as Error).message)
  } finally {
    uploading.value = false
    uploadController = null
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="props.show" @update:open="onOpenChange">
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
          <Input v-model="name" :disabled="locked" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('knowledge.descLabel') }}</label>
          <Input v-model="description" :disabled="locked" />
        </div>

        <!-- 编辑态：内容不可变，只提示 -->
        <div v-if="isRename" class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          {{ $t('knowledge.renameOnly') }}
        </div>

        <!-- 新建态：任意格式文件（点击选择或拖入） -->
        <template v-else>
          <div
            class="file-drop"
            :class="{ over: dragOver, picked: !!file, locked }"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <template v-if="file">
              <FileUp class="size-5 shrink-0" />
              <span class="min-w-0 flex-1 truncate text-sm">{{ file.name }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ humanSize(file.size) }}</span>
              <button
                type="button" class="shrink-0 rounded p-1 hover:bg-accent" :disabled="locked"
                @click="file = null"
              >
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

          <!-- 上传进度：确定性（有 File.size + 进度事件的 loaded），比转圈信息量大 -->
          <div v-if="uploading" class="grid gap-1.5" role="status" aria-live="polite">
            <Progress :value="uploadPct" class="h-2" />
            <p class="text-xs text-muted-foreground">
              {{ $t('knowledge.uploading', {
                loaded: humanSize(uploaded), total: humanSize(uploadTotal), pct: uploadPct,
              }) }}
            </p>
          </div>
          <p v-else class="text-xs text-muted-foreground">
            {{ $t('knowledge.anyFormatHint', { max: MAX_FILE_LABEL }) }}
          </p>
        </template>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <!-- 上传中点它 = 中断上传并关闭（走 onOpenChange，与右上角 X 同一出口） -->
        <Button
          variant="outline" size="sm" :disabled="saving && !uploading" @click="onOpenChange(false)"
        >
          {{ $t('common.cancel') }}
        </Button>
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
/* 上传中锁住拖拽区：中途换文件会让进度与最终落盘的对象对不上 */
.file-drop.locked {
  pointer-events: none;
  opacity: 0.75;
}
</style>
