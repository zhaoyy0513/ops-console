<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NPopconfirm,
  NSpace,
  NTabPane,
  NTabs,
  NTable,
  useMessage,
} from 'naive-ui'
import {
  sitesApi,
  type ResourceConfig,
  type ResourceType,
  type Site,
} from './api'
import ResourceEditModal from './ResourceEditModal.vue'
import FieldMappingDialog from './FieldMappingDialog.vue'

const props = defineProps<{ show: boolean; site: Site | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'changed'): void }>()

const TYPES: Array<{ key: ResourceType; label: string }> = [
  { key: 'servers', label: 'Server' },
  { key: 'redis', label: 'Redis' },
  { key: 'mq', label: 'ActiveMQ' },
  { key: 'robots', label: 'Robot' },
]

/** 各 tab 表格的列定义（编辑表单字段定义在 ResourceEditModal 内） */
const COLUMN_DEFS: Record<ResourceType, Array<{ key: string; label: string }>> = {
  servers: [
    { key: 'host', label: 'Host' },
    { key: 'port', label: 'Port' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  redis: [
    { key: 'host', label: 'Host' },
    { key: 'port', label: 'Port' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  mq: [
    { key: 'host', label: 'Host' },
    { key: 'port', label: 'Port' },
    { key: 'username', label: '用户名' },
    { key: 'password', label: '密码' },
  ],
  robots: [
    { key: 'base_url', label: 'Base URL' },
    { key: 'field_map', label: '字段映射' },
  ],
}

const message = useMessage()
const activeType = ref<ResourceType>('servers')
const items = ref<ResourceConfig[]>([])

const siteId = computed(() => props.site?.id ?? '')
const columns = computed(() => COLUMN_DEFS[activeType.value] ?? [])

/** 编辑弹窗状态（独立组件，与 Drawer 平级渲染——嵌套时焦点陷阱锁输入） */
const editShow = ref(false)
const editTarget = ref<{
  id: string | null
  type: ResourceType
  item: Record<string, any>
  hostOptions: Array<{ label: string; value: string }>
  siteId: string
} | null>(null)

/** Robot 字段映射弹窗 */
const mappingShow = ref(false)
const mappingRobot = ref<ResourceConfig | null>(null)

async function load() {
  if (!props.show || !siteId.value) return
  try {
    items.value = await sitesApi.listResources(siteId.value, activeType.value)
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function loadHostOptions(): Promise<Array<{ label: string; value: string }>> {
  if (!siteId.value) return []
  try {
    const servers = await sitesApi.listResources(siteId.value, 'servers')
    return [...new Set(servers.map((s) => String(s.host)))].map((h) => ({
      label: h,
      value: h,
    }))
  } catch {
    return []
  }
}

watch(
  () => [props.show, siteId.value, activeType.value] as const,
  () => load(),
  { immediate: true },
)

async function openCreate() {
  const hostOptions = activeType.value !== 'robots' ? await loadHostOptions() : []
  editTarget.value = {
    id: null,
    type: activeType.value,
    item: {},
    hostOptions,
    siteId: siteId.value,
  }
  editShow.value = true
}

async function openEdit(item: ResourceConfig) {
  const hostOptions = activeType.value === 'redis' || activeType.value === 'mq'
    ? await loadHostOptions()
    : []
  editTarget.value = {
    id: item.id,
    type: activeType.value,
    item: { ...item },
    hostOptions,
    siteId: siteId.value,
  }
  editShow.value = true
}

function onSaved() {
  load()
  emit('changed')
}

async function remove(item: ResourceConfig) {
  await sitesApi.removeResource(siteId.value, activeType.value, item.id)
  message.success('已删除')
  await load()
}

function displayValue(item: ResourceConfig, key: string): string {
  const v = item[key]
  if (v === undefined || v === '') return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

const hasMapping = computed(() => activeType.value === 'robots')
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
                <th v-for="f in columns" :key="f.key">{{ f.label }}</th>
                <th style="width: 210px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id">
                <td>{{ item.name }}</td>
                <td v-for="f in columns" :key="f.key">
                  {{ displayValue(item, f.key) }}
                </td>
                <td>
                  <n-space :size="4">
                    <n-button size="tiny" @click="openEdit(item)">编辑</n-button>
                    <n-button
                      v-if="hasMapping && item.id"
                      size="tiny"
                      @click="((mappingRobot = item), (mappingShow = true))"
                    >字段映射</n-button>
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
                <td :colspan="columns.length + 2" style="text-align: center; color: #999">
                  暂无配置
                </td>
              </tr>
            </tbody>
          </n-table>
        </n-tab-pane>
      </n-tabs>
    </n-drawer-content>
  </n-drawer>

  <!-- 编辑/新增弹窗：独立组件，与 Drawer 平级（嵌套时焦点陷阱锁输入） -->
  <resource-edit-modal
    v-model:show="editShow"
    :target="editTarget"
    @saved="onSaved"
  />

  <!-- Robot 字段映射弹窗 -->
  <field-mapping-dialog
    v-model:show="mappingShow"
    :site-id="siteId"
    :robot="mappingRobot"
    @saved="onSaved"
  />
</template>
