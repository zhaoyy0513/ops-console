<script setup lang="ts">
import { computed, h, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChevronLeft, ChevronRight, FolderCog, Languages, Moon, ScrollText, Sun, type LucideIcon,
} from 'lucide-vue-next'
import {
  GridOutline, ServerOutline, DocumentTextOutline, LayersOutline,
  PulseOutline, HardwareChipOutline, TerminalOutline, CubeOutline,
} from '@vicons/ionicons5'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { getModules } from '../modules'
import { locale, setLocale } from '../i18n'
import { useSiteStore } from '../stores/site'
import { useThemeStore, type OpsTheme } from '../stores/theme'

const route = useRoute()
const router = useRouter()
const siteStore = useSiteStore()
const themeStore = useThemeStore()

function toggleLocale() {
  setLocale(locale.value === 'zh' ? 'en' : 'zh')
}

const modules = getModules()

/** 模块图标映射（§3.5） */
const MODULE_ICONS: Record<string, Component> = {
  overview: GridOutline,
  server: ServerOutline,
  page: DocumentTextOutline,
  redis: LayersOutline,
  mq: PulseOutline,
  device: HardwareChipOutline,
  ssh: TerminalOutline,
  database: CubeOutline,
}

// 主题明暗二态切换（themeStore 已在上方声明）
function toggleTheme() {
  themeStore.set(themeStore.theme === 'light' ? 'dark' : 'light')
}

// 侧栏折叠（200px ↔ 56px，只藏文字不藏图标）
const collapsed = ref(false)

// 无有效站点时菜单全部置灰（事前可见优于事后弹窗打断），侧栏另有文字提示
const menuOptions = computed(() =>
  modules.map((m) => ({
    label: m.title,
    key: m.routePath,
    disabled: !siteStore.currentSiteId,
    icon: MODULE_ICONS[m.id] ? () => h(MODULE_ICONS[m.id]!) : undefined,
  })),
)
// 路由表按模块生成静态尾段（/console/site/:siteId/redis），不存在 :moduleId 参数，
// route.params.moduleId 恒为 undefined —— 当前模块只能从 path 末段反查。
const activeModule = computed(() =>
  modules.find((m) => route.path.endsWith(`/${m.routePath}`)),
)
const activeKey = computed(() => activeModule.value?.routePath ?? '')

// 自绘 loading bar（替代 naive useLoadingBar）：路由切换 150ms 顶部条
const barProgress = ref(0)
const barVisible = ref(false)
let barTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => route.fullPath,
  () => {
    clearTimeout(barTimer)
    barVisible.value = true
    barProgress.value = 70
    barTimer = setTimeout(() => {
      barProgress.value = 100
      setTimeout(() => (barVisible.value = false), 120)
    }, 150)
  },
)

/** 校验当前 URL 的 siteId：站点被删后立即踢出（响应式，列表/路由变化都触发） */
function ensureValidSite() {
  const current = String(route.params.siteId ?? '')
  if (!route.path.startsWith('/console/site/')) return
  const options = siteStore.options
  if (options.some((o) => o.value === current)) return
  if (options.length) {
    const target = activeModule.value?.routePath ?? modules[0]?.routePath ?? 'overview'
    router.replace(`/console/site/${options[0].value}/${target}`)
  } else if (siteStore.loaded) {
    // 列表已加载且为空/无匹配 → 站点确实没了；未加载完（loaded=false）时勿误判，
    // 等 watch(sites) 触发本函数再校验（否则直达链接会在列表返回前被弹回 /sites）
    siteStore.setSite('')
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
function onSiteSelect(id: string | null) {
  if (!id) return
  const target = activeModule.value?.routePath ?? modules[0]?.routePath
  router.push(`/console/site/${id}/${target}`)
}

const THEME_ICONS: Record<OpsTheme, LucideIcon> = {
  light: Sun,
  dark: Moon,
}
const themeIcon = computed(() => THEME_ICONS[themeStore.theme])
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <div class="brand-mark font-mono">O</div>
        <span class="font-mono text-[15px] font-bold tracking-tight">Ops Console</span>
      </div>
      <Select
        :model-value="siteStore.currentSiteId || ''"
        @update:model-value="onSiteSelect"
      >
        <SelectTrigger class="site-select" :placeholder="$t('layout.selectSite')" />
        <SelectContent>
          <SelectItem v-for="o in siteStore.options" :key="o.value" :value="o.value">
            {{ o.label }}
          </SelectItem>
        </SelectContent>
      </Select>
      <div class="flex-1" />
      <div class="header-actions">
        <Button variant="ghost" size="sm" @click="router.push('/audit')">
          <ScrollText />
          {{ $t('layout.opsLog') }}
        </Button>
        <Button variant="ghost" size="sm" @click="router.push('/sites')">
          <FolderCog />
          {{ $t('layout.sites') }}
        </Button>
        <Button variant="ghost" size="sm" @click="toggleLocale">
          <Languages />
          {{ locale === 'zh' ? 'EN' : '中文' }}
        </Button>
        <!-- 主题切换：明/暗二态 -->
        <Button variant="ghost" size="icon-sm" :title="$t('layout.theme')" @click="toggleTheme">
          <component :is="themeIcon" />
        </Button>
      </div>
    </header>
    <!-- 自绘顶部 loading bar -->
    <div v-if="barVisible" class="fixed left-0 top-0 z-[100] h-0.5 w-full bg-transparent pointer-events-none">
      <div
        class="h-full bg-primary transition-all duration-150"
        :style="{ width: `${barProgress}%` }"
      />
    </div>
    <div class="app-body">
      <aside class="app-sider" :class="{ collapsed }">
        <div v-if="!siteStore.currentSiteId && !collapsed" class="sider-hint">{{ $t('layout.siderHint') }}</div>
        <nav class="sider-menu">
          <button
            v-for="m in menuOptions"
            :key="m.key"
            class="menu-item"
            :class="{ active: activeKey === m.key, disabled: m.disabled, 'menu-item--collapsed': collapsed }"
            :disabled="m.disabled"
            :title="collapsed ? m.label : undefined"
            @click="onMenuSelect(m.key)"
          >
            <component :is="m.icon?.()" class="menu-icon" />
            <span v-if="!collapsed" class="menu-label">{{ m.label }}</span>
          </button>
        </nav>
        <div class="sider-footer">
          <button class="collapse-btn" :title="collapsed ? $t('layout.expand') : $t('layout.collapse')" @click="collapsed = !collapsed">
            <component :is="collapsed ? ChevronRight : ChevronLeft" class="size-4" />
          </button>
          <span v-if="!collapsed" class="build-stamp font-mono">b1028-1000</span>
        </div>
      </aside>
      <main class="app-main">
        <!-- 不包 Transition：out-in 的 leave 队列与快速导航/弹窗卸载存在竞态
            （prevTree.el 为 null 的 parentNode 崩溃），导航反馈由顶部 loading bar 承担 -->
        <router-view v-slot="{ Component }">
          <div :key="route.path" class="route-view">
            <component :is="Component" />
          </div>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  white-space: nowrap;
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 13px;
  font-weight: 700;
}
.sider-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--ops-border);
}
.build-stamp {
  font-size: 10px;
  color: var(--ops-text-3);
}
.collapse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: none;
  border: none;
  border-radius: 6px;
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
/* 菜单：shadcn sidebar 规格——active 块底 + 图标主色 */
.sider-menu {
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  gap: 4px;
}
.menu-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 38px;
  padding: 0 10px;
  border: none;
  border-radius: var(--ops-radius-m);
  background: transparent;
  color: color-mix(in srgb, var(--ops-text-1) 80%, transparent);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease, padding-left 150ms ease;
  white-space: nowrap;
  overflow: hidden;
}
.menu-item:hover:not(.disabled) {
  background: var(--ops-surface-2);
  color: var(--ops-text-1);
}
.menu-item:hover:not(.disabled):not(.active) {
  padding-left: 12px;
}
.menu-item.active {
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--primary);
  font-weight: 500;
}
.menu-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.menu-item--collapsed {
  justify-content: center;
  padding: 0;
}
.menu-icon {
  width: 20px;
  height: 20px;
  flex: none;
}
.menu-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 顶栏操作条：ghost 按钮直接排，去掉外框（shadcn 规格更干净） */
.header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
}
</style>
