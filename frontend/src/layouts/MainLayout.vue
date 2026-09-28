<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NMenu, NSelect } from 'naive-ui'
import { getModules } from '../modules'
import { locale, setLocale } from '../i18n'
import { useSiteStore } from '../stores/site'

const route = useRoute()
const router = useRouter()
const siteStore = useSiteStore()

function toggleLocale() {
  setLocale(locale.value === 'zh' ? 'en' : 'zh')
}

const modules = getModules()
// 无有效站点时菜单全部置灰（事前可见优于事后弹窗打断），侧栏另有文字提示
const menuOptions = computed(() =>
  modules.map((m) => ({
    label: m.title,
    key: m.routePath,
    disabled: !siteStore.currentSiteId,
  })),
)
const activeKey = computed(() => String(route.params.moduleId ?? ''))

/** 校验当前 URL 的 siteId：站点被删后立即踢出（响应式，列表/路由变化都触发） */
function ensureValidSite() {
  const current = String(route.params.siteId ?? '')
  if (!route.path.startsWith('/console/site/')) return
  const options = siteStore.options
  if (options.some((o) => o.value === current)) return
  if (options.length) {
    const target = String(route.params.moduleId ?? modules[0]?.routePath ?? 'overview')
    router.replace(`/console/site/${options[0].value}/${target}`)
  } else {
    siteStore.setSite('') // 站点已删，清空选中态（下拉不再显示老 ID）
    router.replace('/sites')
  }
}

onMounted(() => siteStore.loadSites().then(ensureValidSite))
watch(() => siteStore.sites, ensureValidSite) // 删除站点后立即纠偏
watch(() => route.fullPath, ensureValidSite) // 手输 URL / 后退进入无效站点时兜底

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
        :placeholder="$t('layout.selectSite')"
        :value="siteStore.currentSiteId || null"
        :options="siteStore.options"
        @update:value="onSiteSelect"
      />
      <div style="flex: 1" />
      <div class="header-actions">
        <n-button size="small" quaternary @click="router.push('/audit')">{{ $t('layout.opsLog') }}</n-button>
        <n-button size="small" quaternary @click="router.push('/sites')">{{ $t('layout.sites') }}</n-button>
        <n-button size="small" quaternary @click="toggleLocale">
          {{ locale === 'zh' ? 'EN' : '中文' }}
        </n-button>
      </div>
    </header>
    <div class="app-body">
      <aside class="app-sider">
        <div v-if="!siteStore.currentSiteId" class="sider-hint">{{ $t('layout.siderHint') }}</div>
        <n-menu :value="activeKey" :options="menuOptions" @update:value="onMenuSelect" />
        <div class="sider-footer">
          <span class="build-stamp">b0928-2100</span>
        </div>
      </aside>
      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.sider-footer {
  margin-top: auto;
  padding: 8px 16px;
  border-top: 1px solid #f0f1f3;
}
.build-stamp {
  font-size: 10px;
  color: #b0b3b8;
  font-family: ui-monospace, monospace;
}
.sider-hint {
  padding: 12px 16px;
  color: #999;
  font-size: 12px;
  border-bottom: 1px solid #f0f1f3;
}
/* 顶栏操作条：三个按钮收进一个浅边框圆角容器，按钮本身去背景，悬停高亮 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
  padding: 2px 4px;
}
.header-actions :deep(.n-button) {
  --n-color: transparent;
  --n-color-hover: #f2f3f5;
  --n-color-pressed: #e5e6eb;
}
</style>
