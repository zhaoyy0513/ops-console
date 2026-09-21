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

/** 各类型的专有字段（name/enabled 通用，PRD §5.2） */
const FIELD_DEFS: Record<
  ResourceType,
  Array<{ key: string; label: string; kind?: 'number' | 'password'; required?: boolean }>
> = {
  servers: [
    { key: 'host', label: 'Host', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码', kind: 'password' },
    { key: 'private_key', label: 'SSH 私钥' },
  ],
  redis: [
    { key: 'host', label: 'Host', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码', kind: 'password' },
    { key: 'db', label: 'DB', kind: 'number' },
  ],
  mq: [
    { key: 'host', label: 'Host', required: true },
    { key: 'port', label: 'Port', kind: 'number' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码', kind: 'password' },
  ],
  robots: [
    { key: 'base_url', label: 'Base URL', required: true },
    { key: 'list_path', label: '列表路径' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码', kind: 'password' },
  ],
}

const message = useMessage()
const activeType = ref<ResourceType>('redis')
const items = ref<ResourceConfig[]>([])
const showModal = ref(false)
const editingId = ref<string | null>(null)
// ponytail: 动态表单混合 string/number/password 字段，强类型化 v-model 得不偿失
const form = ref<Record<string, any>>({})

const siteId = computed(() => props.site?.id ?? '')

async function load() {
  if (!props.show || !siteId.value) return
  try {
    items.value = await sitesApi.listResources(siteId.value, activeType.value)
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
  form.value = { name: '' }
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
  // 空值字段不提交（number 控件产生 null；密码空串留空 = 后端保留原值）
  const data = Object.fromEntries(
    Object.entries(form.value).filter(([, v]) => v !== null && v !== undefined && v !== ''),
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
                  {{ f.kind === 'password' ? '******' : displayValue(item, f.key) }}
                </td>
                <td>
                  <n-space :size="4">
                    <!-- 已存资源的行级测试需 per-resource test 端点（T12+，服务端读存储密码），暂只在编辑表单内提供 -->
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
            <n-input
              v-else-if="f.kind === 'password'"
              v-model:value="form[f.key]"
              type="password"
              show-password-on="click"
              :placeholder="editingId ? '留空表示不修改' : '可留空（无密码）'"
            />
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
