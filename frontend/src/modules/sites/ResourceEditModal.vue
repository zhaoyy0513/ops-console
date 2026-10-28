<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import ResourceTestButton from '../../components/ResourceTestButton.vue'
import OpsSwitch from '../../components/OpsSwitch.vue'

export interface EditTarget {
  /** 编辑已有资源的 id；null = 新增 */
  id: string | null
  type: 'servers' | 'knowledge' | 'redis' | 'mq' | 'devices'
  /** 编辑时的初始值（新增时传 {}） */
  item: Record<string, any>
  /** host 联想候选（redis/mq/devices 用） */
  hostOptions: Array<{ label: string; value: string }>
  /** 名称联想候选（redis/mq/devices 用，来自同站点 Server 的名称） */
  nameOptions: Array<{ label: string; value: string }>
  /** 资源所属站点（保存与测试请求的目标） */
  siteId: string
}

const props = defineProps<{
  show: boolean
  target: EditTarget | null
  /** 同站点同类型下的已有资源名（前端即时去重校验；后端另有权威校验） */
  existingNames?: string[]
}>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved'): void
}>()

/** 连接测试类型：不能用 replace(/s$/) —— redis 结尾的 s 会被误删成 "red" */
const TEST_TYPE: Record<string, string> = {
  servers: 'server',
  redis: 'redis',
  mq: 'mq',
  devices: 'device',
}

const TYPES: Record<string, string> = {
  servers: 'Server',
  knowledge: 'Knowledge',
  redis: 'Redis',
  mq: 'ActiveMQ',
  devices: 'Device',
}

/** 字段 label 文案在 i18n `fields.<key>`；ph 为各自占位 key（fieldmap/ph 见 sites 命名空间） */
const FIELD_DEFS: Record<
  string,
  Array<{ key: string; label: string; kind?: 'number' | 'host-input' | 'host-select' | 'name-select' | 'url-input'; ph?: string; required?: boolean }>
> = {
  servers: [
    { key: 'host', label: 'Host', kind: 'host-input', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: 'Username', required: true },
    { key: 'password', label: 'Password', required: true },
  ],
  // knowledge：名称必填、描述选填、链接选填（与 HTML / markdown 多选一时 URL 可空）
  knowledge: [
    { key: 'name', label: 'Name', required: true },
    { key: 'description', label: 'Description' },
    { key: 'url', label: 'URL', kind: 'url-input', required: false },
  ],
  redis: [
    { key: 'name', label: 'Name', kind: 'name-select', required: true },
    { key: 'host', label: 'Host', kind: 'host-select', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: 'Username' },
    { key: 'password', label: 'Password' },
  ],
  mq: [
    { key: 'name', label: 'Name', kind: 'name-select', required: true },
    { key: 'host', label: 'Host', kind: 'host-select', required: true },
    { key: 'port', label: 'Port', kind: 'number', ph: 'mqPortPh' },
    { key: 'username', label: 'Username' },
    { key: 'password', label: 'Password' },
  ],
  devices: [
    { key: 'name', label: 'Name', kind: 'name-select', required: true },
    { key: 'base_url', label: 'Base URL', required: true },
  ],
}

const CREATE_DEFAULTS: Record<string, Record<string, unknown>> = {
  servers: { port: 22 },
  knowledge: { url: '', html: '' },
  redis: { port: 6379 },
  mq: { port: 8161, username: 'prime_admin', password: 'hElloPr1me' },
  devices: {},
}

const { t } = useI18n()
const form = ref<Record<string, any>>({})
const saving = ref(false)
/** 内联校验错误（原 NForm required 星号 + useMessage 校验保留，错误文案就地红字） */
const fieldError = ref<string | null>(null)

const fields = computed(() => FIELD_DEFS[props.target?.type ?? 'servers'] ?? [])
const isEdit = computed(() => !!props.target?.id)
const typeLabel = computed(() => TYPES[props.target?.type ?? ''] ?? '')

import { sitesApi } from './api'
import { prepareKnowledgeData } from './knowledgeForm'

watch(
  () => [props.show, props.target] as const,
  ([show, target]) => {
    if (!show || !target) return
    if (target.id) {
      const copy: Record<string, any> = { ...target.item }
      form.value = copy
    } else {
      form.value = { name: '', ...(CREATE_DEFAULTS[target.type] ?? {}) }
    }
    fieldError.value = null
  },
  { immediate: true },
)

/** .html 单文件上传：读文本进 form.html；非 .html 一律拒（扩展名 + MIME 双判）。
 *  原生 file input：选中即读内容并清空选择，可重复选同一文件。 */
async function onHtmlFile(e: Event) {
  const input = e.target as HTMLInputElement
  const raw = input.files?.[0]
  input.value = '' // 先清空，同一文件可再次选择覆盖
  if (!raw) return
  const name = raw.name.toLowerCase()
  if (!name.endsWith('.html') && raw.type !== 'text/html') {
    message.error(t('knowledge.htmlInvalid'))
    return
  }
  try {
    form.value.html = await raw.text()
    message.success(t('knowledge.htmlLoaded'))
  } catch (err) {
    // 沿用本文件 save()/load() 的原始错误信息惯例（动态 {msg} 无静态 key）
    message.error((err as Error).message)
  }
}

/** name 联想（原 NAutoComplete）：自由输入 + datalist 候选，选中回填、不选保留输入 */
function nameListId(key: string) {
  return `ac-${props.target?.type}-${key}`
}

async function save() {
  const target = props.target
  if (!target) return
  fieldError.value = null
  const name = String(form.value.name ?? '').trim()
  if (!name) {
    fieldError.value = t('common.nameRequired')
    return
  }
  // 同站点同类型下 name 唯一：编辑时排除自身（原名放行）。后端亦作权威校验。
  const originalName = isEdit.value ? String(props.target?.item?.name ?? '') : ''
  const dup = (props.existingNames ?? []).some((n) => n === name && n !== originalName)
  if (dup) {
    fieldError.value = t('sites.nameDuplicate', { name })
    return
  }
  for (const f of fields.value) {
    // url-input 是软必填：knowledge 允许用 HTML/markdown 替代链接，空值由下面的多选一校验裁决
    if (f.kind === 'url-input') continue
    // 编辑态密码留空 = 保持原值（后端脱敏回填，明文不可得；必填约束仅创建时生效）
    if (f.required && !(f.key === 'password' && isEdit.value) && !String(form.value[f.key] ?? '').trim()) {
      fieldError.value = t('sites.fieldRequired', { label: t(`fields.${f.key}`) })
      return
    }
  }
  // knowledge 三选一 + html/markdown 空串剔除在纯函数内（knowledgeForm.test.ts 守护）；
  // 其余类型维持原内联过滤（需通过 name/dup/必填校验，见上）
  let data: Record<string, unknown>
  if (target.type === 'knowledge') {
    const prepared = prepareKnowledgeData(form.value)
    if (prepared.error) {
      fieldError.value = prepared.error === 'nameRequired' ? t('common.nameRequired') : t('knowledge.needOne')
      return
    }
    data = prepared.data ?? {}
  } else {
    data = Object.fromEntries(
      Object.entries(form.value)
        .filter(([k, v]) => v !== null && v !== undefined && !(k === 'html' && typeof v === 'string' && !v.trim())
          && !(k === 'markdown' && typeof v === 'string' && !v.trim())
          && !(k === 'password' && v === '')),
    )
  }
  saving.value = true
  try {
    if (target.id) {
      await sitesApi.updateResource(target.siteId, target.type, target.id, data)
    } else {
      await sitesApi.createResource(target.siteId, target.type, data)
    }
    message.success(t('sites.saved'))
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

/** NInputNumber -> type=number Input：保持 number 数据类型（空串归 undefined，避免提交 ''）。
 *  模板编译器不允许 v-model="fn()"，故用 :model-value + @update:model-value setter。 */
function setNumber(key: string, v: string | number | undefined) {
  form.value[key] = v === undefined || v === null || v === '' ? undefined : Number(v)
}
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="w-[520px] max-w-[92vw]" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ isEdit ? $t('sites.editResource', { type: typeLabel }) : $t('sites.newResource', { type: typeLabel }) }}</DialogTitle>
      </DialogHeader>

      <div class="grid gap-3">
        <div v-if="props.target?.type === 'servers'" class="grid grid-cols-[110px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('common.name') }} <span class="text-destructive">*</span></label>
          <Input v-model="form.name" :placeholder="$t('sites.newName')" />
        </div>
        <div v-if="props.target?.type === 'servers'" class="grid grid-cols-[110px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('common.enabled') }}</label>
          <OpsSwitch v-model:value="form.enabled" />
        </div>
        <template v-for="(f, fi) in fields" :key="f.key">
          <div v-if="fi === 1 && props.target?.type !== 'servers'" class="grid grid-cols-[110px_1fr] items-center gap-3">
            <label class="text-xs text-muted-foreground">{{ $t('common.enabled') }}</label>
            <OpsSwitch v-model:value="form.enabled" />
          </div>
          <div class="grid grid-cols-[110px_1fr] items-center gap-3">
            <label class="text-xs text-muted-foreground">
              {{ $t(`fields.${f.key}`) }} <span v-if="f.required" class="text-destructive">*</span>
            </label>
            <Input
              v-if="f.kind === 'number'"
              :model-value="typeof form[f.key] === 'number' ? form[f.key] : undefined"
              type="number"
              :placeholder="f.ph ? $t(`sites.${f.ph}`) : undefined"
              @update:model-value="(v: string | number | undefined) => setNumber(f.key, v)"
            />
            <!-- 输入优先：自由输入 + datalist 同站点 Server 名称联想，选中回填、不选直接保留输入 -->
            <span v-else-if="f.kind === 'name-select'" class="relative block">
              <Input
                v-model="form[f.key]"
                autocomplete="off"
                :list="nameListId(f.key)"
                :placeholder="$t('sites.nameSelectPh')"
              />
              <datalist :id="nameListId(f.key)">
                <option v-for="o in props.target?.nameOptions ?? []" :key="o.value" :value="o.value" />
              </datalist>
            </span>
            <Input v-else-if="f.kind === 'host-input'" v-model="form[f.key]"
              :placeholder="$t('sites.hostInputPh')" />
            <span v-else-if="f.kind === 'host-select'" class="relative block">
              <Input
                v-model="form[f.key]"
                autocomplete="off"
                :list="nameListId(f.key)"
                :placeholder="(props.target?.hostOptions ?? []).length ? $t('sites.hostSelectPh') : $t('sites.hostInputAddr')"
              />
              <datalist :id="nameListId(f.key)">
                <option v-for="o in props.target?.hostOptions ?? []" :key="o.value" :value="o.value" />
              </datalist>
            </span>
            <!-- knowledge 链接：与 HTML/markdown 多选一，故 required=true 的字段用软校验（save 内判空） -->
            <Input v-else-if="f.kind === 'url-input'" v-model="form[f.key]"
              :placeholder="$t('knowledge.urlPh')" />
            <Input
              v-else
              v-model="form[f.key]"
              :type="f.key === 'password' ? 'password' : undefined"
              :placeholder="f.key === 'password' && isEdit ? $t('sites.passwordKeep') : undefined"
              autocomplete="new-password"
            />
          </div>
        </template>
        <!-- knowledge 专属：HTML 上传 / 粘贴（与 url 二选一，上限单个 .html 文件） -->
        <template v-if="props.target?.type === 'knowledge'">
          <div v-if="props.target?.item?.markdown" class="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            {{ $t('knowledge.drawerMdHint') }}
          </div>
          <div class="grid grid-cols-[110px_1fr] items-center gap-3">
            <label class="text-xs text-muted-foreground">{{ $t('knowledge.typeHtml') }}</label>
            <div class="flex flex-wrap items-center gap-2.5">
              <label class="inline-flex h-7 cursor-pointer items-center rounded-md border border-border px-2 text-xs font-medium hover:bg-accent">
                {{ $t('knowledge.uploadHtml') }}
                <input type="file" accept=".html" class="hidden" @change="onHtmlFile" />
              </label>
            </div>
          </div>
          <div class="grid grid-cols-[110px_1fr] items-start gap-3">
            <span />
            <Textarea
              v-model="form.html"
              :rows="6"
              class="font-mono"
              spellcheck="false"
              :placeholder="$t('knowledge.htmlPh')"
            />
          </div>
        </template>
        <!-- 无连接测试的类型（knowledge：不需要连通性探测）不渲染 Test 行 -->
        <div v-if="TEST_TYPE[props.target?.type ?? 'servers']" class="grid grid-cols-[110px_1fr] items-center gap-3">
          <span />
          <div class="flex items-center gap-2.5">
            <ResourceTestButton :type="TEST_TYPE[props.target?.type ?? 'servers']" :config="form" />
            <span v-if="props.target?.type === 'mq'" class="text-xs text-muted-foreground">
              {{ $t('sites.jolokiaHint') }}
            </span>
          </div>
        </div>
      </div>

      <!-- 校验错误就地红字（原 NForm 提交拦截改自绘，不引 vee-validate） -->
      <p v-if="fieldError" class="text-xs text-destructive">{{ fieldError }}</p>

      <div class="mt-8 flex justify-end gap-2.5">
        <Button variant="outline" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button :disabled="saving" @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
