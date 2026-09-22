<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTable,
  useMessage,
} from 'naive-ui'
import ResourceTestButton from '../../components/ResourceTestButton.vue'
import {
  sitesApi,
  TEST_TYPE,
  type ResourceConfig,
  type ResourceType,
  type Site,
} from './api'

const props = defineProps<{ show: boolean; site: Site | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'changed'): void }>()

const TYPES: Array<{ key: ResourceType; label: string }> = [
  { key: 'servers', label: 'Server' },
  { key: 'redis', label: 'Redis' },
  { key: 'mq', label: 'ActiveMQ' },
  { key: 'robots', label: 'Robot' },
]

/** 各类型的专有字段（name/enabled 通用，PRD §5.2）；required 表单必填。
 *  host 输入形态：server 手输；redis/mq 可输可选（候选 = 同站点 Server 的 host） */
const FIELD_DEFS: Record<
  ResourceType,
  Array<{ key: string; label: string; kind?: 'number' | 'host-input' | 'host-select'; required?: boolean }>
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
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  robots: [{ key: 'base_url', label: 'Base URL', required: true }],
}

/** 新增时的字段预填默认值（现场约定：mq 凭据默认值、端口按协议） */
const CREATE_DEFAULTS: Record<ResourceType, Record<string, unknown>> = {
  servers: { port: 22 },
  redis: { port: 6379 },
  mq: { port: 61616, username: 'prime_admin', password: 'hElloPr1me' },
  robots: {},
}

const message = useMessage()
const activeType = ref<ResourceType>('servers') // 默认最左侧 Server
const items = ref<ResourceConfig[]>([])
const showModal = ref(false)
const editingId = ref<string | null>(null)
// ponytail: 动态表单混合 string/number/password 字段，强类型化 v-model 得不偿失
const form = ref<Record<string, any>>({})

const siteId = computed(() => props.site?.id ?? '')

/** host 下拉候选：同站点已配置 Server 的 host（redis/mq 常与 server 同机） */
const hostOptions = ref<Array<{ label: string; value: string }>>([])

async function load() {
  if (!props.show || !siteId.value) return
  try {
    items.value = await sitesApi.listResources(siteId.value, activeType.value)
    const servers = await sitesApi.listResources(siteId.value, 'servers')
    hostOptions.value = [...new Set(servers.map((s) => String(s.host)))].map((h) => ({
      label: h,
      value: h,
    }))
  } catch (e) {
    message.error((e as Error).message)
  }
}

watch(
  () => [props.show, siteId.value, activeType.value] as const,
  () => load(),
  { immediate: true },
)

function openCreate() {
  editingId.value = null
  form.value = { name: '', ...CREATE_DEFAULTS[activeType.value] }
  showModal.value = true
}

function openEdit(item: ResourceConfig) {
  editingId.value = item.id
  form.value = { ...item } // password 不回显（空串），留空保存 = 不修改
  showModal.value = true
}

async function save() {
  if (!String(form.value.name ?? '').trim()) {
    message.warning('名称必填')
    return
  }
  for (const f of FIELD_DEFS[activeType.value]) {
    if (f.required && !String(form.value[f.key] ?? '').trim()) {
      message.warning(`${f.label} 必填`)
      return
    }
  }
  // 空值字段不提交 null/undefined（number 控件产生 null）；空串照常提交（全明文语义：提交什么存什么）
  const data = Object.fromEntries(
    Object.entries(form.value).filter(([, v]) => v !== null && v !== undefined),
  )
  try {
    if (editingId.value) {
      await sitesApi.updateResource(siteId.value, activeType.value, editingId.value, data)
    } else {
      await sitesApi.createResource(siteId.value, activeType.value, data)
    }
    showModal.value = false
    message.success('已保存')
    await load()
    emit('changed')
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function remove(item: ResourceConfig) {
  await sitesApi.removeResource(siteId.value, activeType.value, item.id)
  message.success('已删除')
  await load()
}

function displayValue(item: ResourceConfig, key: string): string {
  const v = item[key]
  if (v === undefined || v === '') return '-'
  return String(v)
}
</script>

<template>
  <n-drawer :show="props.show" :width="720" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`资源配置 · ${props.site?.name ?? ''}`" closable>
      <n-tabs v-model:value="activeType" type="line" size="small">
        <n-tab-pane v-for="t in TYPES" :key="t.key" :name="t.key" :tab="t.label">
          <n-space justify="end" style="margin-bottom: 8px">
            <n-button size="small" type="primary" @click="openCreate">新增</n-button>
          </n-space>
          <n-table :bordered="false" :single-line="false" size="small">
            <thead>
              <tr>
                <th>名称</th>
                <th v-for="f in FIELD_DEFS[activeType]" :key="f.key">{{ f.label }}</th>
                <th style="width: 150px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id">
                <td>{{ item.name }}</td>
                <td v-for="f in FIELD_DEFS[activeType]" :key="f.key">
                  {{ displayValue(item, f.key) }}
                </td>
                <td>
                  <n-space :size="4">
                    <!-- 已存资源的行级测试需 per-resource test 端点（PRD §18），落地后补 -->
                    <n-button size="tiny" @click="openEdit(item)">编辑</n-button>
                    <n-popconfirm @positive-click="remove(item)">
                      <template #trigger>
                        <n-button size="tiny" type="error" ghost>删除</n-button>
                      </template>
                      删除 {{ item.name }}？
                    </n-popconfirm>
                  </n-space>
                </td>
              </tr>
              <tr v-if="!items.length">
                <td :colspan="FIELD_DEFS[activeType].length + 2" style="text-align: center; color: #999">
                  暂无配置
                </td>
              </tr>
            </tbody>
          </n-table>
        </n-tab-pane>
      </n-tabs>

      <n-modal
        v-model:show="showModal"
        preset="card"
        :title="editingId ? '编辑配置' : `新增 ${TYPES.find((t) => t.key === activeType)?.label} 配置`"
        style="width: 520px"
      >
        <n-form label-placement="left" label-width="90">
          <n-form-item label="名称" required>
            <n-input v-model:value="form.name" placeholder="如：redis-01" />
          </n-form-item>
          <n-form-item label="启用">
            <n-switch v-model:value="form.enabled" :default-value="true" />
          </n-form-item>
          <n-form-item
            v-for="f in FIELD_DEFS[activeType]"
            :key="f.key"
            :label="f.label"
            :required="f.required"
          >
            <n-input-number
              v-if="f.kind === 'number'"
              v-model:value="form[f.key]"
              style="width: 100%"
            />
            <!-- server 手输；redis/mq 可输可选（tag 模式自由输入，候选来自已有 Server） -->
            <n-input v-if="f.kind === 'host-input'" v-model:value="form[f.key]"
              placeholder="IP 或主机名" />
            <n-select
              v-else-if="f.kind === 'host-select'"
              v-model:value="form[f.key]"
              filterable
              tag
              default-first-option
              :options="hostOptions"
              :placeholder="hostOptions.length ? '选择已有 Server 的 Host 或直接输入' : '输入地址'"
            />
            <!-- 内部工具全明文；编辑预填原密码，改动即覆盖 -->
            <n-input v-else v-model:value="form[f.key]" />
          </n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="space-between">
            <!-- 表单内连接测试：无需先保存（PRD §13.1），使用表单当前值 -->
            <resource-test-button :type="TEST_TYPE[activeType]" :config="form" />
            <n-space :size="8">
              <n-button @click="showModal = false">取消</n-button>
              <n-button type="primary" @click="save">保存</n-button>
            </n-space>
          </n-space>
        </template>
      </n-modal>
    </n-drawer-content>
  </n-drawer>
</template>
