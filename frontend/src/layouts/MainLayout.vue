<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NMenu, NSelect } from 'naive-ui'
import { getModules } from '../modules'
import { sitesApi, type Site } from '../modules/sites/api'
import { useSiteStore } from '../stores/site'

const route = useRoute()
const router = useRouter()
const siteStore = useSiteStore()

const modules = getModules()
const menuOptions = modules.map((m) => ({ label: m.title, key: m.routePath }))
const activeKey = computed(() => String(route.params.moduleId ?? ''))

// 站点选项来自后端（T06 API）
const siteOptions = ref<Array<{ label: string; value: string }>>([])

onMounted(async () => {
  try {
    const sites: Site[] = await sitesApi.list()
    siteOptions.value = sites.map((s) => ({ label: s.name, value: s.id }))
  } catch {
    // 后端未就绪时选择器留空，不阻塞页面
  }
})

watch(
  () => route.params.siteId,
  (id) => {
    if (id) siteStore.setSite(String(id))
  },
  { immediate: true },
)

function onMenuSelect(key: string) {
  router.push(`/console/site/${siteStore.currentSiteId || 'demo-site'}/${key}`)
}

// 切换站点后停留在当前模块（PRD §21）
function onSiteSelect(id: string) {
  const target = route.params.moduleId ?? modules[0]?.routePath
  router.push(`/console/site/${id}/${target}`)
}
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <span class="brand">Ops Console</span>
      <n-select
        class="site-select"
        size="small"
        placeholder="选择站点"
        :value="siteStore.currentSiteId || null"
        :options="siteOptions"
        @update:value="onSiteSelect"
      />
      <div style="flex: 1" />
      <n-button size="small" quaternary @click="router.push('/sites')">站点管理</n-button>
    </header>
    <div class="app-body">
      <aside class="app-sider">
        <n-menu :value="activeKey" :options="menuOptions" @update:value="onMenuSelect" />
      </aside>
      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
</template>
