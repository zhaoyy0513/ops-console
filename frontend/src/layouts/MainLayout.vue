<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NMenu, NSelect } from 'naive-ui'
import { getModules } from '../modules'
import { useSiteStore } from '../stores/site'

const route = useRoute()
const router = useRouter()
const siteStore = useSiteStore()

const modules = getModules()
const menuOptions = modules.map((m) => ({ label: m.title, key: m.routePath }))
const activeKey = computed(() => String(route.params.moduleId ?? ''))

onMounted(() => {
  siteStore.loadSites().then(() => {
    // 当前 URL 的 siteId 不存在 → 自动跳第一个真实站点；
    // 一个站点都没有 → 引导去站点管理
    const current = String(route.params.siteId ?? '')
    const options = siteStore.options
    if (route.path.startsWith('/console/site/') && !options.some((o) => o.value === current)) {
      if (options.length) {
        const target = String(route.params.moduleId ?? modules[0]?.routePath ?? 'overview')
        router.replace(`/console/site/${options[0].value}/${target}`)
      } else {
        router.replace('/sites')
      }
    }
  })
})

watch(
  () => route.params.siteId,
  (id) => {
    if (id) siteStore.setSite(String(id))
  },
  { immediate: true },
)

function onMenuSelect(key: string) {
  // 无有效站点时去站点管理，不拼占位 URL（避免 404）
  const siteId = route.params.siteId ?? siteStore.currentSiteId
  router.push(siteId ? `/console/site/${siteId}/${key}` : '/sites')
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
        :options="siteStore.options"
        @update:value="onSiteSelect"
      />
      <div style="flex: 1" />
      <n-button size="small" quaternary @click="router.push('/audit')">操作日志</n-button>
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
