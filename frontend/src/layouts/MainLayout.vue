<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NMenu, NSelect } from 'naive-ui'
import { getModules } from '../modules'
import { useSiteStore } from '../stores/site'

const route = useRoute()
const router = useRouter()
const siteStore = useSiteStore()

const modules = getModules()
const menuOptions = modules.map((m) => ({ label: m.title, key: m.routePath }))
const activeKey = computed(() => String(route.params.moduleId ?? ''))

// 站点列表 API 在 T06 落地，当前为占位项
const siteOptions = [{ label: 'demo-site', value: 'demo-site' }]

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
        :value="siteStore.currentSiteId"
        :options="siteOptions"
        @update:value="onSiteSelect"
      />
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
