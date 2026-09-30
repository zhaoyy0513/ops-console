<script setup lang="ts">
import { computed, h, inject, onMounted, ref, watch, type Component, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NIcon, NMenu, NSelect, useLoadingBar } from 'naive-ui'
import {
  ChevronBackOutline, ChevronForwardOutline, CubeOutline, GridOutline,
  HardwareChipOutline, LayersOutline, MoonOutline, PulseOutline,
  ServerOutline, SunnyOutline, TerminalOutline,
} from '@vicons/ionicons5'
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

/** 模块图标映射（§3.5：outline，两档颜色） */
const MODULE_ICONS: Record<string, Component> = {
  overview: GridOutline,
  server: ServerOutline,
  redis: LayersOutline,
  mq: PulseOutline,
  device: HardwareChipOutline,
  ssh: TerminalOutline,
  database: CubeOutline,
}

// 主题（App.vue provide 的暗色状态）
const opsDark = inject<{ isDark: Ref<boolean>; toggle: () => void }>('opsDark')!

// 侧栏折叠（200px ↔ 56px，只藏文字不藏图标）
const collapsed = ref(false)

// 无有效站点时菜单全部置灰（事前可见优于事后弹窗打断），侧栏另有文字提示
const menuOptions = computed(() =>
  modules.map((m) => ({
    label: m.title,
    key: m.routePath,
    disabled: !siteStore.currentSiteId,
    icon: MODULE_ICONS[m.id]
      ? () => h(NIcon, null, { default: () => h(MODULE_ICONS[m.id]!) })
      : undefined,
  })),
)
// 路由表按模块生成静态尾段（/console/site/:siteId/redis），不存在 :moduleId 参数，
// route.params.moduleId 恒为 undefined —— 当前模块只能从 path 末段反查。
// （旧代码读这个不存在的参数导致：切站点必跳 overview、侧栏高亮从未生效）
const activeModule = computed(() =>
  modules.find((m) => route.path.endsWith(`/${m.routePath}`)),
)
const activeKey = computed(() => activeModule.value?.routePath ?? '')
const loadingBar = useLoadingBar()
watch(() => route.fullPath, () => { loadingBar.start(); setTimeout(() => loadingBar.finish(), 150) })

/** 校验当前 URL 的 siteId：站点被删后立即踢出（响应式，列表/路由变化都触发） */
function ensureValidSite() {
  const current = String(route.params.siteId ?? '')
  if (!route.path.startsWith('/console/site/')) return
  const options = siteStore.options
  if (options.some((o) => o.value === current)) return
  if (options.length) {
    const target = activeModule.value?.routePath ?? modules[0]?.routePath ?? 'overview'
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

// 切换站点后停留在当前模块（PRD §21）——从 path 尾段反查，params.moduleId 不存在
function onSiteSelect(id: string) {
  const target = activeModule.value?.routePath ?? modules[0]?.routePath
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
        <n-button size="small" quaternary :title="$t('layout.theme')" @click="opsDark.toggle">
          <n-icon :component="opsDark.isDark.value ? SunnyOutline : MoonOutline" />
        </n-button>
      </div>
    </header>
    <div class="app-body">
      <aside class="app-sider" :class="{ collapsed }">
        <div v-if="!siteStore.currentSiteId && !collapsed" class="sider-hint">{{ $t('layout.siderHint') }}</div>
        <n-menu
          :value="activeKey"
          :options="menuOptions"
          :collapsed="collapsed"
          :collapsed-width="56"
          :collapsed-icon-size="18"
          @update:value="onMenuSelect"
        />
        <div class="sider-footer">
          <button class="collapse-btn" :title="collapsed ? $t('layout.expand') : $t('layout.collapse')" @click="collapsed = !collapsed">
            <n-icon :component="collapsed ? ChevronForwardOutline : ChevronBackOutline" :size="16" />
          </button>
          <span v-if="!collapsed" class="build-stamp">b0930-1149</span>
        </div>
      </aside>
      <main class="app-main">
        <!-- 路由/站点切换淡入淡出（out-in：旧视图先退再进，掩盖数据重载白屏）。
             Transition 必须动画单元素根：视图组件可能是多根 fragment，
             直接放 component 会导致 out-in 离场无法完成、导航卡死——
             因此包一层带 key 的 div 作为动画目标。 -->
        <router-view v-slot="{ Component }">
          <transition name="ops-fade" mode="out-in">
            <div :key="route.path" class="route-view">
              <component :is="Component" />
            </div>
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.sider-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--ops-border);
}
.build-stamp {
  font-size: 10px;
  color: var(--ops-text-3);
  font-family: var(--ops-font-mono);
}
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex: none;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--ops-text-3);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}
.collapse-btn:hover {
  background: var(--ops-surface-2);
  color: var(--ops-text-1);
}
.sider-hint {
  padding: 12px 16px;
  color: var(--ops-text-3);
  font-size: 12px;
  border-bottom: 1px solid var(--ops-border);
}
/* 菜单激活态左侧 2px 主色条（高度 60%） */
.app-sider :deep(.n-menu-item-content--selected)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 2px;
  background: var(--ops-primary);
}
/* 顶栏操作条：按钮收进一个浅边框圆角容器，按钮本身去背景，悬停高亮 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--ops-border);
  border-radius: 6px;
  padding: 2px 4px;
  flex: none; /* 操作条整体不压缩，空间不足时由 flex-wrap 折到第二行 */
}
.header-actions :deep(.n-button) {
  --n-color: transparent;
  --n-color-hover: var(--ops-surface-2);
  --n-color-pressed: var(--ops-border);
}
</style>
