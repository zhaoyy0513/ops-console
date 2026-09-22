<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSwitch,
  useMessage,
} from 'naive-ui'
import ResourceTestButton from '../../components/ResourceTestButton.vue'

export interface EditTarget {
  /** 编辑已有资源的 id；null = 新增 */
  id: string | null
  type: 'servers' | 'redis' | 'mq' | 'robots'
  /** 编辑时的初始值（新增时传 {}） */
  item: Record<string, any>
  /** host 下拉候选（redis/mq 用） */
  hostOptions: Array<{ label: string; value: string }>
}

const props = defineProps<{ show: boolean; target: EditTarget | null }>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved'): void
}>()

const TYPES: Record<string, string> = {
  servers: 'Server',
  redis: 'Redis',
  mq: 'ActiveMQ',
  robots: 'Robot',
}

const FIELD_DEFS: Record<
  string,
  Array<{ key: string; label: string; kind?: 'number' | 'host-input' | 'host-select'; ph?: string; required?: boolean }>
> = {
  servers: [
    { key: 'host', label: 'Host', kind: 'host-input', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名', required: true },
    { key: 'password', label: '密码', required: true },
  ],
  redis: [
    { key: 'host', label: 'Host', kind: 'host-select', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  mq: [
    { key: 'host', label: 'Host', kind: 'host-select', required: true },
    { key: 'port', label: 'Port', kind: 'number', ph: 'Jolokia HTTP 端口，默认 8161' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  robots: [{ key: 'base_url', label: 'Base URL', required: true }],
}

const CREATE_DEFAULTS: Record<string, Record<string, unknown>> = {
  servers: { port: 22 },
  redis: { port: 6379 },
  mq: { port: 8161, username: 'prime_admin', password: 'hElloPr1me' },
  robots: {},
}

const message = useMessage()
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
    message.warning('名称必填')
    return
  }
  for (const f of fields.value) {
    if (f.required && !String(form.value[f.key] ?? '').trim()) {
      message.warning(`${f.label} 必填`)
      return
    }
  }
  const data = Object.fromEntries(
    Object.entries(form.value).filter(([, v]) => v !== null && v !== undefined),
  )
  saving.value = true
  try {
    if (target.id) {
      await sitesApi.updateResource(target.id && data.__siteId, target.type, target.id, data)
    } else {
      await sitesApi.createResource(data.__siteId, target.type, data)
    }
    message.success('已保存')
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
  <n-modal
    :show="props.show"
    preset="card"
    :title="isEdit ? `编辑 ${typeLabel} 配置` : `新增 ${typeLabel} 配置`"
    style="width: 520px"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="left" label-width="90">
      <n-form-item label="名称" required>
        <n-input v-model:value="form.name" placeholder="如：redis-01" />
      </n-form-item>
      <n-form-item label="启用">
        <n-switch v-model:value="form.enabled" :default-value="true" />
      </n-form-item>
      <n-form-item
        v-for="f in fields"
        :key="f.key"
        :label="f.label"
        :required="f.required"
      >
        <n-input-number
          v-if="f.kind === 'number'"
          v-model:value="form[f.key]"
          style="width: 100%"
          :placeholder="f.ph"
        />
        <n-input v-else-if="f.kind === 'host-input'" v-model:value="form[f.key]"
          placeholder="IP 或主机名" />
        <n-select
          v-else-if="f.kind === 'host-select'"
          v-model:value="form[f.key]"
          filterable
          tag
          default-first-option
          :options="props.target?.hostOptions ?? []"
          :placeholder="(props.target?.hostOptions ?? []).length ? '选择已有 Server 的 Host 或直接输入' : '输入地址'"
        />
        <n-input v-else v-model:value="form[f.key]" />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="footer">
        <div class="footer-test">
          <resource-test-button :type="props.target?.type?.replace(/s$/, '') ?? 'server'" :config="form" />
          <span v-if="props.target?.type === 'mq'" class="hint">
            平台经 Jolokia HTTP(8161) 读取管理数据
          </span>
        </div>
        <n-space justify="end" :size="8">
          <n-button @click="emit('update:show', false)">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.footer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.footer-test {
  padding-left: 90px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint {
  color: #999;
  font-size: 12px;
}
</style>
