<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSpace,
  NSwitch,
  NTable,
  NTag,
  useMessage,
} from 'naive-ui'
import { sitesApi, type Site } from './api'
import { useSiteStore } from '../../stores/site'
import SiteResourcesDrawer from './SiteResourcesDrawer.vue'

const router = useRouter()
const message = useMessage()
const siteStore = useSiteStore()

const showModal = ref(false)
const editing = ref<Site | null>(null)
const form = ref({ name: '', description: '', enabled: true })
const drawerSite = ref<Site | null>(null)
const drawerShow = ref(false)

// 站点列表存于共享 store（顶栏下拉同源），增删后 loadSites() 两处同步
const sites = computed(() => siteStore.sites)

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
    message.warning('站点名称必填')
    return
  }
  try {
    if (editing.value) {
      await sitesApi.update(editing.value.id, form.value)
    } else {
      const site = await sitesApi.create(form.value)
      message.success('已创建，去配置资源？')
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

async function remove(site: Site) {
  try {
    await sitesApi.remove(site.id)
    message.success('已删除')
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
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
  <n-card title="站点管理" size="small">
    <template #header-extra>
      <n-button size="small" type="primary" @click="openCreate">新建站点</n-button>
    </template>

    <n-table :bordered="false" :single-line="false" size="small">
      <thead>
        <tr>
          <th>ID</th>
          <th>名称</th>
          <th>描述</th>
          <th style="width: 90px">启用</th>
          <th style="width: 260px">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sites" :key="s.id">
          <td><n-tag size="small" :bordered="false">{{ s.id }}</n-tag></td>
          <td>{{ s.name }}</td>
          <td>{{ s.description }}</td>
          <td><n-switch size="small" :value="s.enabled" @update:value="toggle(s)" /></td>
          <td>
            <n-space :size="4">
              <n-button size="tiny" @click="openResources(s)">资源</n-button>
              <n-button size="tiny" @click="goConsole(s)">进入</n-button>
              <n-button size="tiny" @click="openEdit(s)">编辑</n-button>
              <n-popconfirm @positive-click="remove(s)">
                <template #trigger>
                  <n-button size="tiny" type="error" ghost>删除</n-button>
                </template>
                删除站点 {{ s.name }} 及其全部资源配置？
              </n-popconfirm>
            </n-space>
          </td>
        </tr>
        <tr v-if="!sites.length">
          <td colspan="5" style="text-align: center; color: #999">暂无站点，点击右上角新建</td>
        </tr>
      </tbody>
    </n-table>
  </n-card>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="editing ? `编辑站点 · ${editing.name}` : '新建站点'"
    style="width: 480px"
  >
    <n-form label-placement="left" label-width="70">
      <n-form-item label="名称">
        <n-input v-model:value="form.name" placeholder="如：深圳测试站" />
      </n-form-item>
      <n-form-item label="描述">
        <n-input v-model:value="form.description" type="textarea" :rows="2" />
      </n-form-item>
      <n-form-item label="启用">
        <n-switch v-model:value="form.enabled" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showModal = false">取消</n-button>
        <n-button type="primary" @click="save">保存</n-button>
      </n-space>
    </template>
  </n-modal>

  <site-resources-drawer v-model:show="drawerShow" :site="drawerSite" @changed="load" />
</template>
