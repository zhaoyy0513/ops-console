<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, FileText, Link2, Maximize2, Minimize2, Plus } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import TipCopy from '../../components/TipCopy.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { useSiteStore } from '../../stores/site'
import PageDialog from './PageDialog.vue'
import { pageApi, derivePageKind, type PageResource } from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const pages = ref<PageResource[]>([])
const loading = ref(false)
const showReader = ref(false)
const active = ref<PageResource | null>(null)

// 新建/编辑两用弹窗状态
const showEditor = ref(false)
const editing = ref<PageResource | null>(null)

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

function startNew() {
  editing.value = null
  showEditor.value = true
}

function startEdit(p: PageResource) {
  editing.value = p
  showEditor.value = true
}

/** 删除确认后执行：抛错时 CountdownConfirm 复位 pending 并保持弹窗，列表不重载 */
async function remove(p: PageResource) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  await pageApi.remove(siteId, p.id)
  message.success(t('page.deleted'))
  await load()
}

/** 卡片点击：url 型新标签打开（X-Frame-Options 类安全策略无法绕过，最可靠）；
 *  html 型站内弹窗阅读（sandbox 隔离）。 */
function open(p: PageResource) {
  const k = derivePageKind(p)
  if (k === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  active.value = p
  showReader.value = true
}

/** 新标签打开：url 直开；html 转外层 sandbox 壳 Blob——与阅读弹窗同一隔离底线
 *  （allow-scripts 可跑、opaque origin 拿不到本域 cookie/storage）。内层用 srcdoc 而非
 *  src="blob:"：sandbox 无 allow-same-origin 时 opaque origin 取 blob: 会被浏览器拦截白屏。
 *  Blob 用完即回收（60s 足够浏览器完成打开动作） */
function openExternal() {
  const p = active.value
  if (!p) return
  const k = derivePageKind(p)
  if (k === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  const html = p.html ?? ''
  if (!html) return
  const inner = html.replace(/&/g, '&amp;').replace(/"/g, '&quot;') // srcdoc 属性转义
  const shell = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%}</style></head><body><iframe sandbox="allow-scripts" srcdoc="${inner}" style="border:0;width:100%;height:100%"></iframe></body></html>`
  const url = URL.createObjectURL(new Blob([shell], { type: 'text/html;charset=utf-8' }))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
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

/** 阅读弹窗防误关（对齐原 modal mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}

const activeSrcDoc = computed(() => active.value?.html ?? '')

function kindLabel(p: PageResource) {
  return derivePageKind(p) === 'url' ? t('page.kindUrl') : t('page.kindHtml')
}
</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('page.title') }}</CardTitle>
      <span class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">{{ $t('page.hintShort') }}</span>
        <tab-help topic="page" />
        <Button size="sm" :disabled="!siteStore.currentSiteId" @click="startNew">
          <Plus />
          {{ $t('page.new') }}
        </Button>
      </span>
    </CardHeader>
    <CardContent>
      <div v-if="loading" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>
      <div v-else-if="pages.length" class="page-grid">
        <fade-content v-for="(p, i) in pages" :key="p.id" :delay="i * 60" class="page-fade">
          <!-- page-card 只做定位容器（无 transform）：删除确认弹窗 fixed 定位不能落在
               带 transform 的祖先里，悬停位移全部移入 .card-lift 内层 -->
          <div class="page-card" @click="open(p)" @mousemove="onCardMove">
            <div class="card-lift">
              <div class="pc-head">
                <span class="pc-title">
                  <Link2 v-if="derivePageKind(p) === 'url'" class="pc-icon" />
                  <FileText v-else class="pc-icon" />
                  {{ p.name }}
                </span>
                <Badge size="sm" :variant="derivePageKind(p) === 'url' ? 'default' : 'secondary'">
                  {{ kindLabel(p) }}
                </Badge>
              </div>
              <div class="pc-desc">{{ p.description }}</div>
              <div v-if="derivePageKind(p) === 'url' && p.url" class="pc-url">
                <tip-copy :text="p.url" :max="280" :copy="false" />
              </div>
            </div>

            <!-- hover 遮罩：打开 / 编辑 / 删除（:focus-within 保证键盘可达） -->
            <div class="card-overlay" @click.stop>
              <button type="button" class="ov-btn" @click="open(p)">{{ $t('page.open') }}</button>
              <button type="button" class="ov-btn" @click="startEdit(p)">{{ $t('page.edit') }}</button>
              <span class="ov-del">
                <countdown-confirm :label="$t('page.del')" :target="p.name" :on-confirm="() => remove(p)" />
              </span>
            </div>
          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('page.empty')" />
    </CardContent>
  </Card>

  <!-- 新建/编辑两用弹窗：站点只读、url/html 二选一、.html 上传 -->
  <PageDialog v-model:show="showEditor" :site-id="siteStore.currentSiteId ?? ''" :editing="editing" @saved="load" />

  <!-- 阅读弹窗：仅 html 型会进来（url 型 open() 直接新标签）；
       sandbox 隔离（allow-scripts 但不 allow-same-origin，
       脚本可运行却拿不到本域 cookie/storage——内部工具嵌入不受信页面的安全底线） -->
  <Dialog :open="showReader" @update:open="showReader = $event">
    <DialogContent
      class="flex h-[88vh] w-[92vw] max-w-none flex-col overflow-hidden"
      :class="isFullscreen && 'page-fullscreen'"
      @escape-key-down="blockDismiss"
      @interact-outside="blockDismiss"
    >
      <DialogHeader>
        <DialogTitle>{{ active?.name ?? '' }}</DialogTitle>
      </DialogHeader>
      <iframe
        v-if="active"
        class="html-frame min-h-0 w-full flex-1"
        sandbox="allow-scripts"
        :srcdoc="activeSrcDoc"
        :title="active.name"
      />
      <DialogFooter class="flex-row items-center justify-between pt-2">
        <span class="frame-note">{{ $t('page.frameNote') }}</span>
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
/* 定位容器：不携带 transform/overflow——删除确认弹窗 fixed 依赖它 */
.page-card {
  position: relative;
  height: 100%;
}
.card-lift {
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
  overflow: hidden;
  cursor: pointer;
  transition:
    transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 160ms ease,
    box-shadow 200ms ease;
}
/* 顶部细渐变条：仅 hover 显形 */
.card-lift::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, var(--primary), transparent 70%);
  opacity: 0;
  transition: opacity 200ms ease;
}
.card-lift::after {
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
.page-card:hover .card-lift {
  transform: translateY(-3px) scale(1.012);
  border-color: var(--primary);
  box-shadow: 0 10px 24px rgba(31, 35, 41, 0.1);
}
.page-card:hover .card-lift::before,
.page-card:hover .card-lift::after {
  opacity: 1;
}
@media (prefers-reduced-motion: reduce) {
  .card-lift { transition: border-color 160ms ease; }
  .page-card:hover .card-lift { transform: none; }
  .card-lift::before, .card-lift::after { transition: none; }
  .card-overlay { transition: none; }
}
.pc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pc-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ops-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-icon {
  width: 14px;
  height: 14px;
  flex: none;
  color: var(--ops-text-3);
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
/* ---- hover 遮罩：深色纱 + 半透明胶囊按钮（两主题通吃） ---- */
.card-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-radius: var(--ops-radius-m);
  background: rgba(15, 18, 24, 0.45);
  opacity: 0;
  pointer-events: none;
  transition: opacity 140ms ease;
}
.page-card:hover .card-overlay,
.page-card:focus-within .card-overlay {
  opacity: 1;
  pointer-events: auto;
}
.ov-btn {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: background 120ms ease;
}
.ov-btn:hover {
  background: rgba(255, 255, 255, 0.28);
}
.ov-btn:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.8);
  outline-offset: 2px;
}
.ov-del {
  display: inline-flex;
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
