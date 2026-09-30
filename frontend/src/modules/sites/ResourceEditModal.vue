<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  useMessage,
} from 'naive-ui'
import ResourceTestButton from '../../components/ResourceTestButton.vue'
import OpsSwitch from '../../components/OpsSwitch.vue'

export interface EditTarget {
  /** 编辑已有资源的 id；null = 新增 */
  id: string | null
  type: 'servers' | 'redis' | 'mq' | 'devices'
  /** 编辑时的初始值（新增时传 {}） */
  item: Record<string, any>
  /** host 下拉候选（redis/mq/devices 用） */
  hostOptions: Array<{ label: string; value: string }>
  /** 名称下拉候选（redis/mq/devices 用，来自同站点 Server 的名称） */
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
  redis: 'Redis',
  mq: 'ActiveMQ',
  devices: 'Device',
}

/** 字段 label 文案在 i18n `fields.<key>`；ph 为各自占位 key（fieldmap/ph 见 sites 命名空间） */
const FIELD_DEFS: Record<
  string,
  Array<{ key: string; label: string; kind?: 'number' | 'host-input' | 'host-select' | 'name-select'; ph?: string; required?: boolean }>
> = {
  servers: [
    { key: 'host', label: 'Host', kind: 'host-input', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: 'Username', required: true },
    { key: 'password', label: 'Password', required: true },
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

async function save() {
  const target = props.target
  if (!target) return
  if (!String(form.value.name ?? '').trim()) {
    message.warning(t('common.nameRequired'))
    return
  }
  for (const f of fields.value) {
    if (f.required && !String(form.value[f.key] ?? '').trim()) {
      message.warning(t('sites.fieldRequired', { label: t(`fields.${f.key}`) }))
      return
    }
  }
  const data = Object.fromEntries(
    Object.entries(form.value).filter(([, v]) => v !== null && v !== undefined),
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
        <n-select
          v-else-if="f.kind === 'name-select'"
          v-model:value="form[f.key]"
          filterable
          tag
          default-first-option
          :options="props.target?.nameOptions ?? []"
          :placeholder="$t('sites.nameSelectPh')"
        />
        <n-input v-else-if="f.kind === 'host-input'" v-model:value="form[f.key]"
          :placeholder="$t('sites.hostInputPh')" />
        <n-select
          v-else-if="f.kind === 'host-select'"
          v-model:value="form[f.key]"
          filterable
          tag
          default-first-option
          :options="props.target?.hostOptions ?? []"
          :placeholder="(props.target?.hostOptions ?? []).length ? $t('sites.hostSelectPh') : $t('sites.hostInputAddr')"
        />
        <n-input v-else v-model:value="form[f.key]" />
        </n-form-item>
      </template>
      <n-form-item label=" ">
        <div class="form-test">
          <resource-test-button :type="TEST_TYPE[props.target?.type ?? 'servers'] ?? 'server'" :config="form" />
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
