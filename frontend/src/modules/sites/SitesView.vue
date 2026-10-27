<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { LoaderCircle, Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogTitle,
  AlertDialogBody,
  AlertDialogCancel,
  AlertDialogContent,
} from '@/components/ui/alert-dialog'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
import { sitesApi, type Site } from './api'
import { useSiteStore } from '../../stores/site'
import SiteResourcesDrawer from './SiteResourcesDrawer.vue'
import OpsSwitch from '../../components/OpsSwitch.vue'
import OpsDataTable from '../../components/OpsDataTable.vue'

const router = useRouter()
const { t } = useI18n()
const siteStore = useSiteStore()

const showModal = ref(false)
const editing = ref<Site | null>(null)
const form = ref({ name: '', description: '', enabled: true })
const drawerSite = ref<Site | null>(null)
const drawerShow = ref(false)
const deleteTarget = ref<Site | null>(null)

// 站点列表存于共享 store（顶栏下拉同源），增删后 loadSites() 两处同步
const sites = computed(() => siteStore.sites)

// 列表列（ID/名称/描述可排序；开关与操作列不排——排序由 OpsDataTable 内建处理）
const columns = computed<any[]>(() => [
  {
    accessorKey: 'id',
    header: 'ID',
    cell: (ctx: any) =>
      h('span', { class: 'font-mono text-xs text-muted-foreground' }, String(ctx.row.original.id)),
  },
  {
    accessorKey: 'name',
    header: t('common.name'),
    cell: (ctx: any) => h('span', { class: 'font-medium' }, ctx.row.original.name),
  },
  {
    accessorKey: 'description',
    header: t('sites.desc'),
    cell: (ctx: any) => h('span', { class: 'text-muted-foreground' }, ctx.row.original.description),
  },
  {
    accessorKey: 'enabled',
    header: t('common.enabled'),
    enableSorting: false,
    cell: (ctx: any) =>
      h(OpsSwitch, {
        value: ctx.row.original.enabled,
        'onUpdate:value': () => toggle(ctx.row.original),
      }),
  },
  {
    id: 'actions',
    header: t('common.actions'),
    enableSorting: false,
    cell: (ctx: any) =>
      h('div', { class: 'flex items-center gap-1' }, [
        h(Button, { variant: 'ghost', size: 'sm', onClick: () => openResources(ctx.row.original) }, () => t('sites.resourcesBtn')),
        h(Button, { variant: 'ghost', size: 'sm', onClick: () => goConsole(ctx.row.original) }, () => t('sites.enterBtn')),
        h(Button, { variant: 'ghost', size: 'sm', onClick: () => openEdit(ctx.row.original) }, () => t('common.edit')),
        h(
          Button,
          { variant: 'ghost', size: 'sm', class: 'text-destructive hover:text-destructive', onClick: () => (deleteTarget.value = ctx.row.original) },
          () => t('common.delete'),
        ),
      ]),
  },
])

async function load() {
  await siteStore.loadSites()
}
onMounted(load)

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', enabled: true }
  showModal.value = true
}

function openEdit(site: Site) {
  editing.value = site
  form.value = { name: site.name, description: site.description, enabled: site.enabled }
  showModal.value = true
}

async function save() {
  if (!form.value.name.trim()) {
    message.warning(t('sites.nameRequired'))
    return
  }
  try {
    if (editing.value) {
      await sitesApi.update(editing.value.id, form.value)
    } else {
      const site = await sitesApi.create(form.value)
      message.success(t('sites.created'))
      drawerSite.value = site
      drawerShow.value = true
    }
    showModal.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function toggle(site: Site) {
  await sitesApi.update(site.id, { enabled: !site.enabled })
  await load()
}

/** 删除中：禁用确定按钮并转圈，防连点重复提交 */
const deleting = ref(false)

async function remove(site: Site) {
  deleting.value = true
  try {
    await sitesApi.remove(site.id)
    message.success(t('sites.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    deleting.value = false
  }
}

/** AlertDialogAction 关窗事件先于 @click 把 deleteTarget 清空，先取快照再删 */
function confirmDelete() {
  if (deleting.value) return
  const target = deleteTarget.value
  deleteTarget.value = null
  if (target) void remove(target)
}

function openResources(site: Site) {
  drawerSite.value = site
  drawerShow.value = true
}

function goConsole(site: Site) {
  router.push(`/console/site/${site.id}/overview`)
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ $t('sites.title') }}</CardTitle>
      <template #action>
        <Button size="sm" @click="openCreate">
          <Plus class="size-3.5" />
          {{ $t('sites.newSite') }}
        </Button>
      </template>
    </CardHeader>
    <CardContent class="px-0 pb-2">
      <OpsDataTable :columns="columns" :data="sites" row-key="id" :empty-text="$t('sites.empty')" />
    </CardContent>
  </Card>

  <!-- 新增/编辑站点 -->
  <Dialog v-model:open="showModal">
    <DialogContent class="w-[480px] max-w-[92vw]" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ editing ? $t('sites.editTitle', { name: editing.name }) : $t('sites.newSite') }}</DialogTitle>
      </DialogHeader>
      <div class="grid gap-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('common.name') }}</label>
          <Input v-model="form.name" :placeholder="$t('sites.namePh')" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-start gap-3">
          <label class="pt-1.5 text-xs text-muted-foreground">{{ $t('sites.desc') }}</label>
          <Textarea v-model="form.description" :rows="2" />
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <label class="text-xs text-muted-foreground">{{ $t('common.enabled') }}</label>
          <OpsSwitch v-model:value="form.enabled" />
        </div>
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" @click="showModal = false">{{ $t('common.cancel') }}</Button>
        <Button @click="save">{{ $t('common.save') }}</Button>
      </div>
    </DialogContent>
  </Dialog>

  <!-- 删除确认（原 NPopconfirm -> AlertDialog，整窗级渲染避免单元格内弹层） -->
  <AlertDialog :open="deleteTarget !== null" @update:open="(v: boolean) => { if (!v) deleteTarget = null }">
    <AlertDialogContent>
      <AlertDialogBody>
        <AlertDialogTitle class="text-base font-semibold">{{ $t('common.confirm') }}</AlertDialogTitle>
        <p class="text-sm text-muted-foreground">{{ $t('sites.deleteConfirm', { name: deleteTarget?.name ?? '' }) }}</p>
      </AlertDialogBody>
      <div class="flex justify-end gap-2 pt-3">
        <AlertDialogCancel :disabled="deleting">{{ $t('common.cancel') }}</AlertDialogCancel>
        <AlertDialogAction :disabled="deleting" @click="confirmDelete">
          <span class="inline-flex items-center gap-1.5">
            <LoaderCircle v-if="deleting" class="size-3.5 animate-spin" />
            {{ deleting ? $t('common.processing') : $t('common.delete') }}
          </span>
        </AlertDialogAction>
      </div>
    </AlertDialogContent>
  </AlertDialog>

  <SiteResourcesDrawer v-model:show="drawerShow" :site="drawerSite" @changed="load" />
</template>
