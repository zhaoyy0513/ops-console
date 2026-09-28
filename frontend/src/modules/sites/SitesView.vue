<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
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
const { t } = useI18n()
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

async function remove(site: Site) {
  try {
    await sitesApi.remove(site.id)
    message.success(t('sites.deleted'))
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
  <n-card :title="$t('sites.title')" size="small">
    <template #header-extra>
      <n-button size="small" type="primary" @click="openCreate">{{ $t('sites.newSite') }}</n-button>
    </template>

    <n-table :bordered="false" :single-line="false" size="small">
      <thead>
        <tr>
          <th>ID</th>
          <th>{{ $t('common.name') }}</th>
          <th>{{ $t('sites.desc') }}</th>
          <th style="width: 90px">{{ $t('common.enabled') }}</th>
          <th style="width: 260px">{{ $t('common.actions') }}</th>
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
              <n-button size="tiny" @click="openResources(s)">{{ $t('sites.resourcesBtn') }}</n-button>
              <n-button size="tiny" @click="goConsole(s)">{{ $t('sites.enterBtn') }}</n-button>
              <n-button size="tiny" @click="openEdit(s)">{{ $t('common.edit') }}</n-button>
              <n-popconfirm @positive-click="remove(s)">
                <template #trigger>
                  <n-button size="tiny" type="error" ghost>{{ $t('common.delete') }}</n-button>
                </template>
                {{ $t('sites.deleteConfirm', { name: s.name }) }}
              </n-popconfirm>
            </n-space>
          </td>
        </tr>
        <tr v-if="!sites.length">
          <td colspan="5" style="text-align: center; color: #999">{{ $t('sites.empty') }}</td>
        </tr>
      </tbody>
    </n-table>
  </n-card>

  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="editing ? $t('sites.editTitle', { name: editing.name }) : $t('sites.newSite')"
    style="width: 480px"
  >
    <n-form label-placement="left" label-width="70">
      <n-form-item :label="$t('common.name')">
        <n-input v-model:value="form.name" :placeholder="$t('sites.namePh')" />
      </n-form-item>
      <n-form-item :label="$t('sites.desc')">
        <n-input v-model:value="form.description" type="textarea" :rows="2" />
      </n-form-item>
      <n-form-item :label="$t('common.enabled')">
        <n-switch v-model:value="form.enabled" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showModal = false">{{ $t('common.cancel') }}</n-button>
        <n-button type="primary" @click="save">{{ $t('common.save') }}</n-button>
      </n-space>
    </template>
  </n-modal>

  <site-resources-drawer v-model:show="drawerShow" :site="drawerSite" @changed="load" />
</template>
