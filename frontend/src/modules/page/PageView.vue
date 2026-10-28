<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ExternalLink, FileText, Link, Maximize2, Minimize2 } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import TipCopy from '../../components/TipCopy.vue'
import { useSiteStore } from '../../stores/site'
import { pageApi, type PageResource } from './api'

const siteStore = useSiteStore()

const pages = ref<PageResource[]>([])
const loading = ref(false)
const showHtml = ref(false)
const active = ref<PageResource | null>(null)

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const all = await pageApi.list(siteId)
    pages.value = all.filter((p) => p.enabled !== false) // 停用的不进卡片墙
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => siteStore.currentSiteId, load)

/** 卡片点击：url 型新标签打开（X-Frame-Options 类安全策略无法绕过，最可靠）；
 *  html 型站内弹窗预览（sandbox 隔离）。 */
function open(p: PageResource) {
  if (p.kind === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  preview(p)
}

/** 放大图标：站内弹窗预览（url 型会被部分站点拒绝嵌入 → 弹窗内有新标签兜底） */
function preview(p: PageResource) {
  active.value = p
  showHtml.value = true
}

/** 新标签打开（两种类型都支持）：url 型直接开；html 型转 Blob URL（内容快照，
 *  打开的是生成瞬间的副本）。Blob 用完即回收 */
function openExternal() {
  const p = active.value
  if (!p) return
  if (p.kind === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  if (p.html) {
    const blob = new Blob([p.html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
}

// ---- 弹窗全屏：CSS 铺屏（page-fullscreen 类），不是浏览器 F11——
// 弹窗自身铺满当前视口，内容随之拉伸；Esc 关弹窗行为不变 ----
const isFullscreen = ref(false)

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

/** 卡片聚光跟随：只写 CSS 变量，不进响应式状态、不触发重渲 */
function onCardMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--px', `${e.clientX - r.left}px`)
  el.style.setProperty('--py', `${e.clientY - r.top}px`)
}

/** 危险确认弹窗防误关（对齐原 modal mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}

const activeSrcDoc = computed(() => active.value?.html ?? '')
/** URL 型页面：站内 iframe 预览（目标站可能禁止嵌入，弹窗内提供外链兜底） */
const isUrlKind = computed(() => active.value?.kind === 'url')

</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('page.title') }}</CardTitle>
      <span class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">{{ $t('page.hintShort') }}</span>
        <tab-help topic="page" />
      </span>
    </CardHeader>
    <CardContent>
      <div v-if="loading" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>
      <div v-else-if="pages.length" class="page-grid">
        <fade-content v-for="(p, i) in pages" :key="p.id" :delay="i * 60" class="page-fade">
          <div class="page-card" @click="open(p)" @mousemove="onCardMove">
            <div class="pc-head">
              <span class="pc-title">{{ p.name }}</span>
              <span class="pc-kind">
                <component :is="p.kind === 'html' ? FileText : Link" class="size-3.5" />
                <Badge size="sm" :variant="p.kind === 'html' ? 'secondary' : 'default'">
                  {{ p.kind === 'html' ? $t('page.kindHtml') : $t('page.kindUrl') }}
                </Badge>
                <Maximize2 class="pc-expand" :title="$t('page.preview')" />
              </span>
            </div>
            <div class="pc-desc">{{ p.description }}</div>
            <div v-if="p.kind === 'url' && p.url" class="pc-url">
              <tip-copy :text="p.url" :max="280" :copy="false" />
            </div>
          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('page.empty')" />
    </CardContent>
  </Card>

  <!-- HTML 型页面站内预览：sandbox 隔离（allow-scripts 但不 allow-same-origin，
       脚本可运行却拿不到本域 cookie/storage——内部工具嵌入不受信页面的安全底线） -->
  <Dialog :open="showHtml" @update:open="showHtml = $event">
    <DialogContent
      class="flex h-[88vh] w-[92vw] max-w-none flex-col overflow-hidden"
      :class="isFullscreen && 'page-fullscreen'"
      @escape-key-down="blockDismiss"
      @interact-outside="blockDismiss"
    >
      <DialogHeader>
        <DialogTitle>{{ active?.name ?? '' }}</DialogTitle>
      </DialogHeader>
      <!-- URL 型：直接 src 嵌入（无 sandbox——目标站需自带隔离；禁止嵌入时显示兜底按钮） -->
      <iframe
        v-if="active && isUrlKind && active.url"
        class="html-frame min-h-0 w-full flex-1"
        :src="active.url"
        :title="active.name"
      />
      <iframe
        v-else-if="active"
        class="html-frame min-h-0 w-full flex-1"
        sandbox="allow-scripts"
        :srcdoc="activeSrcDoc"
        :title="active.name"
      />
      <DialogFooter class="flex-row items-center justify-between pt-2">
        <span class="frame-note">
          {{ isUrlKind ? $t('page.frameBlocked') : $t('page.frameNote') }}
        </span>
        <span class="flex items-center gap-2">
          <Button variant="outline" size="sm" :title="isFullscreen ? $t('page.exitFullscreen') : $t('page.fullscreen')" @click="toggleFullscreen">
            <Minimize2 v-if="isFullscreen" />
            <Maximize2 v-else />
          </Button>
          <Button v-if="active" variant="outline" size="sm" @click="openExternal">
            <ExternalLink />
            {{ $t('page.openExternal') }}
          </Button>
        </span>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.page-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.page-fade {
  display: block;
  height: 100%;
}
/* FadeContent 内层 div 也要撑满，否则卡片高度不一致（等高网格） */
.page-fade :deep(.fade-content) {
  height: 100%;
}
.page-card {
  position: relative;
  height: 100%;
  min-height: 108px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 18px;
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  background: var(--ops-surface);
  cursor: pointer;
  overflow: hidden;
  transition:
    transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 160ms ease,
    box-shadow 200ms ease;
}
/* 顶部细渐变条：内容型用主色、链接型用中性色（仅 hover 显形） */
.page-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, var(--ops-primary), transparent 70%);
  opacity: 0;
  transition: opacity 200ms ease;
}
.page-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(
    320px circle at var(--px, 50%) var(--py, 0%),
    rgba(37, 99, 235, 0.07),
    transparent 65%
  );
  opacity: 0;
  transition: opacity 200ms ease;
  pointer-events: none;
}
.page-card:hover {
  transform: translateY(-3px) scale(1.012);
  border-color: var(--ops-primary);
  box-shadow: 0 10px 24px rgba(31, 35, 41, 0.1);
}
.page-card:hover::before,
.page-card:hover::after {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .page-card { transition: border-color 160ms ease; }
  .page-card:hover { transform: none; }
  .page-card::before, .page-card::after { transition: none; }
}
.pc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ops-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-kind {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  color: var(--ops-text-3);
}
/* 放大图标：默认淡显，卡片 hover 时提亮，提示可点开预览 */
.pc-preview {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  color: var(--ops-primary);
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  opacity: 0;
  transition: opacity 120ms ease;
}
.page-card:hover .pc-preview {
  opacity: 1;
}
.pc-preview:hover {
  background: color-mix(in srgb, var(--primary) 25%, transparent);
}
.pc-expand {
  width: 14px;
  height: 14px;
  margin-left: 2px;
  opacity: 0;
  transition: opacity 120ms ease;
}
.page-card:hover .pc-expand {
  opacity: 0.7;
}
.pc-desc {
  font-size: 12px;
  color: var(--ops-text-2);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.pc-url {
  margin-top: auto;
  font-size: 12px;
  color: var(--ops-text-3);
  overflow: hidden;
}
.html-frame {
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  background: var(--ops-surface);
}
.frame-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
</style>
