<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, FileText, Maximize2, Minimize2, Plus } from 'lucide-vue-next'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { useSiteStore } from '../../stores/site'
import KnowledgeDialog from './KnowledgeDialog.vue'
import { classifyDropFiles, compressImage, knowledgeApi, type KnowledgeDoc } from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const docs = ref<KnowledgeDoc[]>([])
const loading = ref(false)
const showReader = ref(false)
const active = ref<KnowledgeDoc | null>(null)

// 新建/改名两用弹窗状态；prefill = 拖拽预填
const showEditor = ref(false)
const editing = ref<KnowledgeDoc | null>(null)
const prefill = ref<{ name?: string; markdown?: string } | null>(null)

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    const all = await knowledgeApi.list(siteId)
    docs.value = all.filter((d) => d.enabled !== false) // 停用的不进卡片墙
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
  prefill.value = null
  showEditor.value = true
}

function startRename(d: KnowledgeDoc) {
  editing.value = d
  prefill.value = null
  showEditor.value = true
}

/** 删除确认后执行：抛错时 CountdownConfirm 复位 pending 并保持弹窗，列表不重载 */
async function remove(d: KnowledgeDoc) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  await knowledgeApi.remove(siteId, d.id)
  message.success(t('knowledge.deleted'))
  await load()
}

/** 查看文档（阅读弹窗，应用内渲染） */
function open(d: KnowledgeDoc) {
  active.value = d
  showReader.value = true
}

// ---- 整域拖放：.md 为正文、图片压缩内嵌 → 预填新建弹窗 ----
const dragging = ref(false)

function onDragLeave(e: DragEvent) {
  // 子元素间移动会触发 dragleave，仅真正离开容器时收起提示
  if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragging.value = false
}

async function onDrop(e: DragEvent) {
  dragging.value = false
  const files = [...(e.dataTransfer?.files ?? [])]
  if (!files.length) return
  const { markdownFiles, imageFiles } = classifyDropFiles(files)
  if (!markdownFiles.length && !imageFiles.length) return
  let markdown = ''
  let name = ''
  if (markdownFiles.length) {
    try {
      markdown = await markdownFiles[0].text()
      name = markdownFiles[0].name.replace(/\.(md|markdown)$/i, '')
    } catch (err) {
      message.error((err as Error).message)
      return
    }
  }
  for (const img of imageFiles) {
    try {
      markdown = markdown ? `${markdown}\n\n![](${await compressImage(img)})` : `![](${await compressImage(img)})`
      if (!name) name = img.name.replace(/\.[^.]+$/, '')
    } catch { /* 压缩失败忽略该张 */ }
  }
  if (!markdown) return
  editing.value = null
  prefill.value = { name, markdown }
  showEditor.value = true
}

/** 新标签打开：渲染后 HTML 装进外层 sandbox 壳 Blob——与阅读弹窗同一隔离底线
 *  （allow-scripts 可跑、opaque origin 拿不到本域 cookie/storage）。内层用 srcdoc 而非
 *  src="blob:"：sandbox 无 allow-same-origin 时 opaque origin 取 blob: 会被浏览器拦截白屏。
 *  Blob 用完即回收（60s 足够浏览器完成打开动作） */
function openExternal() {
  if (!renderedMd.value) return
  const inner = renderedMd.value.replace(/&/g, '&amp;').replace(/"/g, '&quot;') // srcdoc 属性转义
  const shell = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%}</style></head><body><iframe sandbox="allow-scripts" srcdoc="${inner}" style="border:0;width:100%;height:100%"></iframe></body></html>`
  const url = URL.createObjectURL(new Blob([shell], { type: 'text/html;charset=utf-8' }))
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** markdown 渲染：marked 解析后必须过 DOMPurify 白名单（内容来自用户粘贴的任意文本） */
const renderedMd = computed(() =>
  active.value
    ? DOMPurify.sanitize(marked.parse(active.value.markdown ?? '', { async: false }) as string)
    : '',
)

// ---- 弹窗全屏：CSS 铺屏（page-fullscreen 类），不是浏览器 F11；Esc 关弹窗行为不变 ----
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
</script>

<template>
  <Card>
    <CardHeader class="flex-row items-center justify-between">
      <CardTitle>{{ $t('knowledge.title') }}</CardTitle>
      <span class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">{{ $t('knowledge.hintShort') }}</span>
        <tab-help topic="knowledge" />
        <Button size="sm" :disabled="!siteStore.currentSiteId" @click="startNew">
          <Plus />
          {{ $t('knowledge.new') }}
        </Button>
      </span>
    </CardHeader>
    <!-- 整域 dropzone：拖入 .md / 图片直接预填新建 -->
    <CardContent
      class="relative"
      @dragover.prevent="dragging = true"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div v-if="dragging" class="drop-hint" data-test="drop-hint">
        <FileText class="size-6" />
        {{ $t('knowledge.dragHint') }}
      </div>
      <div v-if="loading" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>
      <div v-else-if="docs.length" class="page-grid">
        <fade-content v-for="(d, i) in docs" :key="d.id" :delay="i * 60" class="page-fade">
          <!-- page-card 只做定位容器（无 transform）：删除确认弹窗 fixed 定位不能落在
               带 transform 的祖先里，悬停位移全部移入 .card-lift 内层 -->
          <div class="page-card" @click="open(d)" @mousemove="onCardMove">
            <div class="card-lift">
              <div class="pc-head">
                <span class="pc-title">
                  <FileText class="pc-icon" />
                  {{ d.name }}
                </span>
              </div>
              <div class="pc-desc">{{ d.description }}</div>
            </div>

            <!-- hover 遮罩：查看 / 重命名 / 删除（:focus-within 保证键盘可达） -->
            <div class="card-overlay" @click.stop>
              <button type="button" class="ov-btn" @click="open(d)">{{ $t('knowledge.open') }}</button>
              <button type="button" class="ov-btn" @click="startRename(d)">{{ $t('knowledge.rename') }}</button>
              <span class="ov-del">
                <countdown-confirm :label="$t('knowledge.del')" :target="d.name" :on-confirm="() => remove(d)" />
              </span>
            </div>
          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('knowledge.empty')" />
    </CardContent>
  </Card>

  <!-- 新建/改名两用弹窗：新建含 Markdown 编辑器（上传 .md / 上传图片 / 粘贴图内嵌） -->
  <KnowledgeDialog
    v-model:show="showEditor"
    :site-id="siteStore.currentSiteId ?? ''"
    :editing="editing"
    :prefill="prefill"
    @saved="load"
  />

  <!-- 阅读弹窗：应用内渲染（DOMPurify 消毒），跟随主题 -->
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
      <div class="md-reader min-h-0 flex-1 overflow-y-auto" v-html="renderedMd" />
      <DialogFooter class="flex-row items-center justify-end pt-2">
        <span class="flex items-center gap-2">
          <Button variant="outline" size="sm" :title="isFullscreen ? $t('knowledge.exitFullscreen') : $t('knowledge.fullscreen')" @click="toggleFullscreen">
            <Minimize2 v-if="isFullscreen" />
            <Maximize2 v-else />
          </Button>
          <Button variant="outline" size="sm" @click="openExternal">
            <ExternalLink />
            {{ $t('knowledge.openExternal') }}
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
/* ---- 拖放提示层 ---- */
.drop-hint {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 2px dashed color-mix(in srgb, var(--primary) 55%, transparent);
  border-radius: var(--ops-radius-m);
  background: color-mix(in srgb, var(--primary) 8%, transparent);
  color: var(--primary);
  font-size: 14px;
  pointer-events: none;
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
.ov-del :deep(button) {
  border-radius: 999px;
}
/* ---- 应用内 markdown 阅读样式（最小 prose，跟随主题 token） ---- */
.md-reader {
  padding: 4px 8px;
  color: var(--ops-text-1);
  font-size: 14px;
  line-height: 1.7;
}
.md-reader :deep(h1),
.md-reader :deep(h2),
.md-reader :deep(h3) {
  color: var(--ops-text-1);
  font-weight: 600;
  margin: 1.2em 0 0.5em;
  line-height: 1.35;
}
.md-reader :deep(h1) { font-size: 1.5em; border-bottom: 1px solid var(--ops-border); padding-bottom: 0.3em; }
.md-reader :deep(h2) { font-size: 1.25em; }
.md-reader :deep(h3) { font-size: 1.1em; }
.md-reader :deep(h1:first-child),
.md-reader :deep(h2:first-child),
.md-reader :deep(h3:first-child) { margin-top: 0; }
.md-reader :deep(p) { margin: 0.6em 0; }
.md-reader :deep(ul),
.md-reader :deep(ol) { margin: 0.6em 0; padding-left: 1.6em; }
.md-reader :deep(li) { margin: 0.25em 0; }
.md-reader :deep(a) { color: var(--primary); }
.md-reader :deep(code) {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.9em;
  background: color-mix(in srgb, var(--ops-text-3) 12%, transparent);
  border-radius: 4px;
  padding: 0.15em 0.4em;
}
.md-reader :deep(pre) {
  background: color-mix(in srgb, var(--ops-text-3) 10%, transparent);
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  padding: 12px 14px;
  overflow-x: auto;
  margin: 0.8em 0;
}
.md-reader :deep(pre code) { background: none; padding: 0; font-size: 13px; }
.md-reader :deep(img) { max-width: 100%; border-radius: 6px; margin: 0.6em 0; }
.md-reader :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.2em 1em;
  border-left: 3px solid var(--ops-border);
  color: var(--ops-text-2);
}
.md-reader :deep(table) {
  border-collapse: collapse;
  margin: 0.8em 0;
  font-size: 13px;
}
.md-reader :deep(th),
.md-reader :deep(td) {
  border: 1px solid var(--ops-border);
  padding: 6px 10px;
  text-align: left;
}
.md-reader :deep(th) { background: color-mix(in srgb, var(--ops-text-3) 8%, transparent); font-weight: 600; }
</style>
