<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
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
  { key: 'devices', label: 'Device' },
]

/** 各 tab 表格的列定义（编辑表单字段定义在 ResourceEditModal 内）；列头文案在 i18n fields.<key> */
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
  devices: [
    { key: 'base_url', label: 'Base URL' },
  ],
}

const message = useMessage()
const { t } = useI18n()
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
  nameOptions: Array<{ label: string; value: string }>
  siteId: string
} | null>(null)

/** Device 字段映射弹窗 */
const mappingShow = ref(false)
const mappingDevice = ref<ResourceConfig | null>(null)

async function load() {
  if (!props.show || !siteId.value) return
  try {
    items.value = await sitesApi.listResources(siteId.value, activeType.value)
  } catch (e) {
    message.error((e as Error).message)
  }
}

/** 同站点 Server 候选（host / 名称），供 redis/mq/devices 快速选择 */
async function loadServerOptions(): Promise<{
  hostOptions: Array<{ label: string; value: string }>
  nameOptions: Array<{ label: string; value: string }>
}> {
  if (!siteId.value) return { hostOptions: [], nameOptions: [] }
  try {
    const servers = await sitesApi.listResources(siteId.value, 'servers')
    return {
      hostOptions: [...new Set(servers.map((x) => String(x.host)))].map((h) => ({ label: h, value: h })),
      nameOptions: [...new Set(servers.map((x) => String(x.name)))].map((n) => ({ label: n, value: n })),
    }
  } catch {
    return { hostOptions: [], nameOptions: [] }
  }
}

watch(
  () => [props.show, siteId.value, activeType.value] as const,
  () => load(),
  { immediate: true },
)

async function openCreate() {
  const { hostOptions, nameOptions } = activeType.value !== 'servers'
    ? await loadServerOptions()
    : { hostOptions: [], nameOptions: [] }
  editTarget.value = {
    id: null,
    type: activeType.value,
    item: {},
    hostOptions,
    nameOptions,
    siteId: siteId.value,
  }
  editShow.value = true
}

async function openEdit(item: ResourceConfig) {
  const { hostOptions, nameOptions } = activeType.value !== 'servers'
    ? await loadServerOptions()
    : { hostOptions: [], nameOptions: [] }
  editTarget.value = {
    id: item.id,
    type: activeType.value,
    item: { ...item },
    hostOptions,
    nameOptions,
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
  message.success(t('sites.deleted'))
  await load()
}

function displayValue(item: ResourceConfig, key: string): string {
  const v = item[key]
  if (v === undefined || v === '') return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

const hasMapping = computed(() => activeType.value === 'devices')
</script>

<template>
  <n-drawer :mask-closable="false" :close-on-esc="false" :show="props.show" :width="720" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="$t('sites.resourcesTitle', { name: props.site?.name ?? '' })" closable>
      <n-tabs v-model:value="activeType" type="line" size="small">
        <n-tab-pane v-for="t in TYPES" :key="t.key" :name="t.key" :tab="t.label">
          <n-space justify="end" style="margin-bottom: 8px">
            <n-button size="small" type="primary" @click="openCreate">{{ $t('common.add') }}</n-button>
          </n-space>
          <n-table :bordered="false" :single-line="false" size="small">
            <thead>
              <tr>
                <th>{{ $t('common.name') }}</th>
                <th v-for="f in columns" :key="f.key">{{ $t(`fields.${f.key}`) }}</th>
                <th style="width: 210px">{{ $t('common.actions') }}</th>
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
                    <n-button size="tiny" @click="openEdit(item)">{{ $t('common.edit') }}</n-button>
                    <n-button
                      v-if="hasMapping && item.id"
                      size="tiny"
                      @click="((mappingDevice = item), (mappingShow = true))"
                    >{{ $t('sites.mappingBtn') }}</n-button>
                    <n-popconfirm @positive-click="remove(item)">
                      <template #trigger>
                        <n-button size="tiny" type="error" ghost>{{ $t('common.delete') }}</n-button>
                      </template>
                      {{ $t('sites.deleteResourceConfirm', { name: item.name }) }}
                    </n-popconfirm>
                  </n-space>
                </td>
              </tr>
              <tr v-if="!items.length">
                <td :colspan="columns.length + 2" style="text-align: center; color: #999">
                  {{ $t('sites.emptyResources') }}
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

  <!-- Device 字段映射弹窗 -->
  <field-mapping-dialog
    v-model:show="mappingShow"
    :site-id="siteId"
    :device="mappingDevice"
    @saved="onSaved"
  />
</template>
