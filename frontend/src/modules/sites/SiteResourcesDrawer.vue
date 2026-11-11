<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { LoaderCircle } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import OpsSwitch from '../../components/OpsSwitch.vue'
import {
  AlertDialog,
  AlertDialogTitle,
  AlertDialogBody,
  AlertDialogContent,
} from '@/components/ui/alert-dialog'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { message } from '@/lib/message'
import {
  sitesApi,
  type ResourceConfig,
  type ResourceType,
  type Site,
} from './api'
import ResourceEditModal from './ResourceEditModal.vue'
import FieldMappingDialog from './FieldMappingDialog.vue'
import OpsDataTable from '../../components/OpsDataTable.vue'

const props = defineProps<{ show: boolean; site: Site | null }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'changed'): void }>()
const router = useRouter()

const TYPES: Array<{ key: ResourceType; label: string }> = [
  { key: 'servers', label: 'Server' },
  { key: 'pages', label: 'Page' },
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
  pages: [
    { key: 'description', label: '描述' },
    { key: 'url', label: '链接' },
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

const { t } = useI18n()
const activeType = ref<ResourceType>('servers')
const items = ref<ResourceConfig[]>([])

const siteId = computed(() => props.site?.id ?? '')

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

const deleteTarget = ref<ResourceConfig | null>(null)

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

/** 删除中：禁用确定按钮，防连点重复提交 */
const deleting = ref(false)

async function remove(item: ResourceConfig) {
  if (deleting.value) return
  deleting.value = true
  try {
    await sitesApi.removeResource(siteId.value, activeType.value, item.id)
    message.success(t('sites.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    deleting.value = false
  }
}

/** 确认删除：显式关窗按钮直接调这里（不再依赖 reka Action 的自动关闭——
 *  其内部 close 先于 fallthrough @click 执行，会提前清空 deleteTarget） */
function confirmDelete() {
  if (deleting.value || !deleteTarget.value) return
  const target = deleteTarget.value
  deleteTarget.value = null
  void remove(target)
}

function displayValue(item: ResourceConfig, key: string): string {
  // 密码列：接口已脱敏（不回明文），按 has_password 显示掩码
  if (key === 'password') return item.has_password ? '••••••••' : '-'
  const v = item[key]
  if (v === undefined || v === '') return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** 页面资源"进入"：url 型直接开外链，html 型进 console 的 page 模块查看渲染 */
function enterPage(row: ResourceConfig) {
  const url = row.url ? String(row.url) : ''
  if (url) {
    window.open(url, '_blank', 'noopener')
    return
  }
  router.push(`/console/site/${siteId.value}/page`)
}

/** 行内启停：与站点列表一致走局部更新，None 表示不改（后端部分更新语义） */
async function toggleEnabled(row: ResourceConfig) {
  await sitesApi.updateResource(siteId.value, activeType.value, row.id, {
    enabled: !row.enabled,
  })
  await load()
}

/** 每个 tab 一组列（启用 + name + 类型字段 + [类别] + 操作）；操作列不排 */
const columns = computed<any[]>(() => {
  const isPage = activeType.value === 'pages'
  const actionButtons = (row: ResourceConfig) => {
    const btns: ReturnType<typeof h>[] = []
    if (isPage && (row.url || row.html)) {
      btns.push(
        h(Button, { variant: 'ghost', size: 'sm', onClick: () => enterPage(row) }, () => t('sites.enterBtn')),
      )
    }
    if (activeType.value === 'devices' && row.id) {
      btns.push(
        h(
          Button,
          { variant: 'ghost', size: 'sm', onClick: () => { mappingDevice.value = row; mappingShow.value = true } },
          () => t('sites.mappingBtn'),
        ),
      )
    }
    btns.push(
      h(Button, { variant: 'ghost', size: 'sm', onClick: () => openEdit(row) }, () => t('common.edit')),
      h(
        Button,
        { variant: 'ghost', size: 'sm', class: 'text-destructive hover:text-destructive', onClick: () => (deleteTarget.value = row) },
        () => t('common.delete'),
      ),
    )
    return btns
  }
  const kindBadge = (row: ResourceConfig) => {
    // 与后端 kind 派生同规则派生（url > html 两档），
    // 不依赖后端版本是否带回 kind 字段
    const kind = row.url ? 'url' : row.html ? 'html' : null
    return kind
      ? h(Badge, { variant: kind === 'url' ? 'secondary' : 'default', size: 'sm' }, () => kind)
      : h('span', { class: 'text-muted-foreground' }, '-')
  }
  return [
    {
      id: 'enabled',
      header: t('common.enabled'),
      enableSorting: false,
      cell: (ctx: any) =>
        h(OpsSwitch, {
          value: ctx.row.original.enabled,
          'onUpdate:value': () => toggleEnabled(ctx.row.original),
        }),
    },
    { accessorKey: 'name', header: t('common.name'), cell: (ctx: any) => h('span', { class: 'font-medium' }, ctx.row.original.name) },
    ...COLUMN_DEFS[activeType.value].map((f) => ({
      accessorKey: f.key,
      header: t(`fields.${f.key}`),
      // 长值（base_url 等）截断显示：抽屉宽度有限，杜绝表格横向滚动条
      cell: (ctx: any) => {
        const v = displayValue(ctx.row.original, f.key)
        return h('span', { class: 'block max-w-[180px] truncate', title: v }, v)
      },
    })),
    ...(isPage
      ? [
          {
            id: 'kind',
            header: t('sites.kind'),
            cell: (ctx: any) => kindBadge(ctx.row.original),
          },
        ]
      : []),
    {
      id: 'actions',
      header: t('common.actions'),
      enableSorting: false,
      cell: (ctx: any) => h('div', { class: 'flex items-center gap-1' }, actionButtons(ctx.row.original)),
    },
  ]
})
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="flex h-[560px] w-[720px] max-w-[94vw] flex-col overflow-hidden" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ $t('sites.resourcesTitle', { name: props.site?.name ?? '' }) }}</DialogTitle>
      </DialogHeader>
      <!-- 新增按钮与 Tabs 同行右侧（原挤在 Tabs 与表格之间贴顶） -->
      <div class="flex items-center justify-between">
        <Tabs v-model="activeType">
          <TabsList class="justify-start">
            <TabsTrigger v-for="tp in TYPES" :key="tp.key" :value="tp.key">{{ tp.label }}</TabsTrigger>
          </TabsList>
        </Tabs>
        <Button size="sm" @click="openCreate">{{ $t('common.add') }}</Button>
      </div>
      <!-- 固定内容区高度：弹窗打开即定型，数据到达不再跳变 -->
      <Tabs v-model="activeType" class="flex-1 overflow-hidden">
        <TabsContent v-for="tp in TYPES" :key="tp.key" :value="tp.key" class="mt-0">
          <div class="max-h-[420px] overflow-auto">
            <OpsDataTable
              :columns="columns"
              :data="items"
              row-key="id"
              :empty-text="$t('sites.emptyResources')"
            />
          </div>
        </TabsContent>
      </Tabs>
    </DialogContent>
  </Dialog>

  <!-- 删除确认（原 NPopconfirm -> AlertDialog） -->
  <AlertDialog :open="deleteTarget !== null" @update:open="(v: boolean) => { if (!v) deleteTarget = null }">
    <AlertDialogContent>
      <AlertDialogBody>
        <AlertDialogTitle class="text-base font-semibold">{{ $t('common.confirm') }}</AlertDialogTitle>
        <p class="text-sm text-muted-foreground">{{ $t('sites.deleteResourceConfirm', { name: deleteTarget?.name ?? '' }) }}</p>
      </AlertDialogBody>
      <div class="flex justify-end gap-2 pt-3">
        <!-- 显式关窗（不用 reka Action/Cancel 的自动关闭）：其内部 close 先于
             fallthrough @click 执行，会把 confirmDelete 要读的 deleteTarget 提前清空 -->
        <Button variant="outline" size="sm" :disabled="deleting" @click="deleteTarget = null">
          {{ $t('common.cancel') }}
        </Button>
        <Button variant="destructive" size="sm" :disabled="deleting" @click="confirmDelete">
          <span class="inline-flex items-center gap-1.5">
            <LoaderCircle v-if="deleting" class="size-3.5 animate-spin" />
            {{ deleting ? $t('common.processing') : $t('common.delete') }}
          </span>
        </Button>
      </div>
    </AlertDialogContent>
  </AlertDialog>

  <!-- 编辑/新增弹窗：独立组件，与 Drawer 平级（嵌套时焦点陷阱锁输入） -->
  <ResourceEditModal
    v-model:show="editShow"
    :target="editTarget"
    :existing-names="items.map((r) => r.name)"
    @saved="onSaved"
  />

  <!-- Device 字段映射弹窗 -->
  <FieldMappingDialog
    v-model:show="mappingShow"
    :site-id="siteId"
    :device="mappingDevice"
    @saved="onSaved"
  />
</template>
