<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAutoComplete,
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NUpload,
  useMessage,
  type UploadFileInfo,
} from 'naive-ui'
import ResourceTestButton from '../../components/ResourceTestButton.vue'
import OpsSwitch from '../../components/OpsSwitch.vue'

export interface EditTarget {
  /** 编辑已有资源的 id；null = 新增 */
  id: string | null
  type: 'servers' | 'pages' | 'redis' | 'mq' | 'devices'
  /** 编辑时的初始值（新增时传 {}） */
  item: Record<string, any>
  /** host 联想候选（redis/mq/devices 用） */
  hostOptions: Array<{ label: string; value: string }>
  /** 名称联想候选（redis/mq/devices 用，来自同站点 Server 的名称） */
  nameOptions: Array<{ label: string; value: string }>
  /** 资源所属站点（保存与测试请求的目标） */
  siteId: string
}

const props = defineProps<{ show: boolean; target: EditTarget | null }>()
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
  pages: 'Page',
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
  // pages：名称/描述/链接 三项必填（用户要求）；HTML 上传块在模板另行渲染
  pages: [
    { key: 'name', label: 'Name', required: true },
    { key: 'description', label: 'Description', required: true },
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
  pages: { url: '', html: '' },
  redis: { port: 6379 },
  mq: { port: 8161, username: 'prime_admin', password: 'hElloPr1me' },
  devices: {},
}

const message = useMessage()
const { t } = useI18n()
const form = ref<Record<string, any>>({})
const saving = ref(false)

const fields = computed(() => FIELD_DEFS[props.target?.type ?? 'servers'] ?? [])
const isEdit = computed(() => !!props.target?.id)
const typeLabel = computed(() => TYPES[props.target?.type ?? ''] ?? '')

import { computed } from 'vue'
import { sitesApi } from './api'

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
  },
  { immediate: true },
)

/** .html 单文件上传：读文本进 form.html；非 .html 一律拒（扩展名 + MIME 双判）。
 *  返回值 false = 不让文件进入 naive 的上传队列（内容已进表单，列表无意义）。 */
async function onHtmlUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file
  const name = (file.name ?? '').toLowerCase()
  if (!name.endsWith('.html') && file.type !== 'text/html') {
    message.error(t('page.invalidHtml'))
    return false
  }
  try {
    const raw = (file.file as File | undefined) ?? null
    if (!raw) throw new Error('no file handle')
    form.value.html = await raw.text()
    message.success(t('page.htmlLoaded'))
  } catch (e) {
    message.error(t('page.htmlFailed', { msg: (e as Error).message }))
  }
  return false
}

function onHtmlRemove(): boolean {
  form.value.html = ''
  return true
}

async function save() {
  const target = props.target
  if (!target) return
  if (!String(form.value.name ?? '').trim()) {
    message.warning(t('common.nameRequired'))
    return
  }
  for (const f of fields.value) {
    // url-input 是软必填：pages 允许用 HTML 替代链接，空值由下面的二选一校验裁决
    if (f.kind === 'url-input') continue
    if (f.required && !String(form.value[f.key] ?? '').trim()) {
      message.warning(t('sites.fieldRequired', { label: t(`fields.${f.key}`) }))
      return
    }
  }
  // pages：url 与 html 至少一个（与后端 PageConfig 同规则）
  if (target.type === 'pages'
    && !String(form.value.url ?? '').trim()
    && !String(form.value.html ?? '').trim()) {
    message.warning(t('page.needOne'))
    return
  }
  const data = Object.fromEntries(
    Object.entries(form.value)
      .filter(([k, v]) => v !== null && v !== undefined && !(k === 'html' && typeof v === 'string' && !v.trim())),
  )
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
</script>

<template>
  <n-modal :mask-closable="false" :close-on-esc="false"
    :show="props.show"
    preset="card"
    :title="isEdit ? $t('sites.editResource', { type: typeLabel }) : $t('sites.newResource', { type: typeLabel })"
    style="width: 520px"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="left" label-width="110">
      <n-form-item v-if="props.target?.type === 'servers'" :label="$t('common.name')" required>
        <n-input v-model:value="form.name" :placeholder="$t('sites.newName')" />
      </n-form-item>
      <n-form-item v-if="props.target?.type === 'servers'" :label="$t('common.enabled')">
        <ops-switch v-model:value="form.enabled" />
      </n-form-item>
      <template v-for="(f, fi) in fields" :key="f.key">
        <n-form-item v-if="fi === 1 && props.target?.type !== 'servers'" :label="$t('common.enabled')">
          <ops-switch v-model:value="form.enabled" />
        </n-form-item>
        <n-form-item
          :label="$t(`fields.${f.key}`)"
          :required="f.required"
        >
        <n-input-number
          v-if="f.kind === 'number'"
          v-model:value="form[f.key]"
          style="width: 100%"
          :placeholder="f.ph ? $t(`sites.${f.ph}`) : undefined"
        />
        <!-- 输入优先：NAutoComplete 自由输入 + 同站点 Server 名称联想，选中回填、不选直接保留输入 -->
        <n-auto-complete
          v-else-if="f.kind === 'name-select'"
          v-model:value="form[f.key]"
          :options="props.target?.nameOptions ?? []"
          :filter="() => true"
          :input-props="{ autocomplete: 'off' }"
          :placeholder="$t('sites.nameSelectPh')"
        />
        <n-input v-else-if="f.kind === 'host-input'" v-model:value="form[f.key]"
          :placeholder="$t('sites.hostInputPh')" />
        <n-auto-complete
          v-else-if="f.kind === 'host-select'"
          v-model:value="form[f.key]"
          :options="props.target?.hostOptions ?? []"
          :filter="() => true"
          :input-props="{ autocomplete: 'off' }"
          :placeholder="(props.target?.hostOptions ?? []).length ? $t('sites.hostSelectPh') : $t('sites.hostInputAddr')"
        />
        <!-- pages 链接：与 HTML 二选一，故 required=true 的字段用软校验（save 内判空） -->
        <n-input v-else-if="f.kind === 'url-input'" v-model:value="form[f.key]"
          :placeholder="$t('page.urlPh')" />
        <n-input v-else v-model:value="form[f.key]" />
        </n-form-item>
      </template>
      <!-- pages 专属：HTML 上传 / 粘贴（与 url 二选一，上限单个 .html 文件） -->
      <template v-if="props.target?.type === 'pages'">
        <n-form-item :label="$t('page.htmlLabel')">
          <div class="html-block">
            <n-upload
              :max="1"
              accept=".html"
              :show-file-list="false"
              :on-before-upload="onHtmlUpload"
              :on-remove="onHtmlRemove"
            >
              <n-button size="small">{{ $t('page.uploadBtn') }}</n-button>
            </n-upload>
            <span class="hint">{{ $t('page.uploadHint') }}</span>
          </div>
        </n-form-item>
        <n-form-item label=" ">
          <n-input
            v-model:value="form.html"
            type="textarea"
            :rows="6"
            class="mono"
            :input-props="{ spellcheck: false }"
            :placeholder="$t('page.htmlPh')"
          />
        </n-form-item>
      </template>
      <!-- 无连接测试的类型（pages：不需要连通性探测）不渲染 Test 行 -->
      <n-form-item v-if="TEST_TYPE[props.target?.type ?? 'servers']" label=" ">
        <div class="form-test">
          <resource-test-button :type="TEST_TYPE[props.target?.type ?? 'servers']" :config="form" />
          <span v-if="props.target?.type === 'mq'" class="hint">
            {{ $t('sites.jolokiaHint') }}
          </span>
        </div>
      </n-form-item>
      <n-form-item label=" ">
        <div class="form-actions">
          <n-button @click="emit('update:show', false)">{{ $t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="saving" @click="save">{{ $t('common.save') }}</n-button>
        </div>
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<style scoped>
.html-block {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.html-block .hint {
  color: var(--ops-text-3);
  font-size: 12px;
}
.form-test {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  width: 100%;
  margin-top: 34px; /* 与 Test 行隔约一个按钮高度的留白 */
}
.hint {
  color: #999;
  font-size: 12px;
}
</style>
