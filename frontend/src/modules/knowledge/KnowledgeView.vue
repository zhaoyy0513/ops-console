<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronLeft, ChevronRight, File, FileText, Image, Music, Plus, Video,
} from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { useSiteStore } from '../../stores/site'
import KnowledgeDialog from './KnowledgeDialog.vue'
import KnowledgeViewer from './KnowledgeViewer.vue'
import {
  contentUrl, fileExt, humanSize, knowledgeApi, MAX_FILE_LABEL, previewKind, validateUpload, type KnowledgeDoc,
} from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const docs = ref<KnowledgeDoc[]>([])
const loading = ref(false)

const showEditor = ref(false)
const editing = ref<KnowledgeDoc | null>(null)
const prefillFile = ref<File | null>(null)

const showViewer = ref(false)
const active = ref<KnowledgeDoc | null>(null)

// ---- 分页：文档多时卡片墙一屏放不下；纯前端分页（元数据很轻，列表一次取回） ----
const PAGE_SIZE = 12
const page = ref(1)
const pageCount = computed(() => Math.max(1, Math.ceil(docs.value.length / PAGE_SIZE)))
const paged = computed(() =>
  docs.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
)

const siteName = computed(
  () => siteStore.options.find((o) => o.value === siteStore.currentSiteId)?.label ?? '',
)

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    docs.value = await knowledgeApi.list(siteId)
    if (page.value > pageCount.value) page.value = pageCount.value
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => siteStore.currentSiteId, () => {
  page.value = 1
  load()
})

function startNew() {
  editing.value = null
  prefillFile.value = null
  showEditor.value = true
}

function startRename(d: KnowledgeDoc) {
  editing.value = d
  prefillFile.value = null
  showEditor.value = true
}

function open(d: KnowledgeDoc) {
  active.value = d
  showViewer.value = true
}

async function remove(d: KnowledgeDoc) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  await knowledgeApi.remove(siteId, d.id)
  message.success(t('knowledge.deleted'))
  await load()
}

// ---- 整域拖放：任意格式文件直接进新建弹窗 ----
const dragging = ref(false)

function onDragLeave(e: DragEvent) {
  if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragging.value = false
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  const err = validateUpload(file)
  if (err) {
    message.error(t(err, { max: MAX_FILE_LABEL }))
    return
  }
  editing.value = null
  prefillFile.value = file
  showEditor.value = true
}

// 兜底：拖到卡片/弹窗之外的区域松手时，浏览器默认会「打开该文件」把页面顶掉。
// 全局拦截并在未处理过的情况下按拖入处理——任何位置拖进来都有反馈。
function onWindowDragOver(e: DragEvent) {
  e.preventDefault()
}

function onWindowDrop(e: DragEvent) {
  if (e.defaultPrevented) return // 卡片/弹窗内已处理（@drop.prevent）
  e.preventDefault()
  onDrop(e)
}

onMounted(() => {
  window.addEventListener('dragover', onWindowDragOver)
  window.addEventListener('drop', onWindowDrop)
})
onBeforeUnmount(() => {
  window.removeEventListener('dragover', onWindowDragOver)
  window.removeEventListener('drop', onWindowDrop)
})

const KIND_ICON = {
  image: Image, pdf: FileText, video: Video, audio: Music, text: FileText, office: FileText, other: File,
} as const

const KIND_LABEL: Record<string, string> = {
  image: 'knowledge.kindImage',
  pdf: 'knowledge.kindPdf',
  video: 'knowledge.kindVideo',
  audio: 'knowledge.kindAudio',
  text: 'knowledge.kindText',
  office: 'knowledge.kindOffice',
  other: 'knowledge.kindOther',
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
    <CardContent
      class="relative"
      @dragover.prevent="dragging = true"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div v-if="dragging" class="drop-hint">
        <span class="drop-chip">
          <FileText class="size-4" />
          {{ $t('knowledge.dragHint') }}
        </span>
      </div>

      <div v-if="loading" class="flex justify-center py-12">
        <span class="inline-block size-6 animate-spin rounded-full border-2 border-border border-t-muted-foreground" />
      </div>
      <div v-else-if="docs.length" class="page-grid">
        <fade-content v-for="(d, i) in paged" :key="d.id" :delay="i * 40" class="page-fade">
          <!-- 悬停位移作用在 .card-lift 上；遮罩嵌在其内一起位移（删除确认弹窗已 Teleport 到 body，不受 transform 影响） -->
          <div class="page-card" @click="open(d)">
            <div class="card-lift">
              <div class="pc-head">
                <span class="pc-title">
                  <component :is="KIND_ICON[previewKind(d)]" class="pc-icon" />
                  {{ d.name }}
                </span>
                <Badge size="sm" variant="secondary">{{ $t(KIND_LABEL[previewKind(d)]) }}</Badge>
              </div>
              <div class="pc-file">
                <span class="truncate">{{ d.filename }}</span>
              </div>
              <div v-if="d.description" class="pc-desc">{{ d.description }}</div>
              <!-- 底部一行：左侧扩展名、右侧文件大小，同一基线 -->
              <div class="pc-foot">
                <span class="pc-ext">{{ fileExt(d).toUpperCase() || 'FILE' }}</span>
                <span class="pc-size">{{ humanSize(d.size) }}</span>
              </div>

              <!-- hover 遮罩放在位移层内：与卡片一起抬起，不再露出缝隙。
                   预览器不认识的格式（other）首按钮是「下载」而非「查看」 -->
              <div class="card-overlay" @click.stop>
                <a v-if="previewKind(d) === 'other'" :href="contentUrl(siteStore.currentSiteId ?? '', d.id)" :download="d.filename" class="ov-btn">
                  {{ $t('knowledge.download') }}
                </a>
                <button v-else type="button" class="ov-btn" @click="open(d)">{{ $t('knowledge.open') }}</button>
                <button type="button" class="ov-btn" @click="startRename(d)">{{ $t('knowledge.rename') }}</button>
                <span class="ov-del">
                  <countdown-confirm :label="$t('knowledge.del')" :target="d.name" :on-confirm="() => remove(d)" />
                </span>
              </div>
            </div>

          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('knowledge.empty')" />

      <!-- 分页 -->
      <div v-if="pageCount > 1" class="pager">
        <Button variant="outline" size="sm" :disabled="page <= 1" @click="page--">
          <ChevronLeft />
        </Button>
        <span class="pager-info">{{ $t('knowledge.pageInfo', { page, total: pageCount }) }}</span>
        <Button variant="outline" size="sm" :disabled="page >= pageCount" @click="page++">
          <ChevronRight />
        </Button>
      </div>
    </CardContent>
  </Card>

  <KnowledgeDialog
    v-model:show="showEditor"
    :site-id="siteStore.currentSiteId ?? ''"
    :site-name="siteName"
    :editing="editing"
    :prefill-file="prefillFile"
    @saved="load"
  />

  <KnowledgeViewer
    v-model:show="showViewer"
    :site-id="siteStore.currentSiteId ?? ''"
    :doc="active"
  />
</template>

<style scoped>
.page-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.page-fade {
  display: block;
  height: 100%;
}
.page-fade :deep(.fade-content) {
  height: 100%;
}
/* 卡片：视觉与位移都在 .card-lift；遮罩嵌在其内，随卡片一起抬起（不再露缝） */
.page-card {
  position: relative;
  height: 100%;
}
.card-lift {
  position: relative;
  height: 100%;
  min-height: 104px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
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
.page-card:hover .card-lift {
  transform: translateY(-3px) scale(1.012);
  border-color: var(--primary);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--ops-text-1) 16%, transparent);
}
@media (prefers-reduced-motion: reduce) {
  .card-lift { transition: border-color 160ms ease; }
  .page-card:hover .card-lift { transform: none; }
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
  color: var(--primary);
}
.pc-file {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--ops-text-2);
  min-width: 0;
}
/* 底部一行：扩展名（左）+ 文件大小（右） */
.pc-foot {
  margin-top: auto;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.pc-size {
  flex: none;
  font-size: 11px;
  color: var(--ops-text-3);
  font-variant-numeric: tabular-nums;
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
.pc-ext {
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--ops-text-3);
  font-family: var(--ops-font-mono);
}
/* ---- 拖放提示层：虚线框 + 居中小胶囊（不罩暗纱） ---- */
.drop-hint {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed color-mix(in srgb, var(--primary) 55%, transparent);
  border-radius: var(--ops-radius-m);
  pointer-events: none;
}
.drop-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--primary) 40%, transparent);
  background: var(--ops-dialog);
  backdrop-filter: blur(8px);
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
/* ---- hover 遮罩 ---- */
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
/* 仅键盘聚焦显形：点开查看弹窗再关闭不会残留遮罩态 */
.page-card:hover .card-overlay,
.page-card:has(:focus-visible) .card-overlay {
  opacity: 1;
  pointer-events: auto;
}
.ov-btn {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--ops-border);
  background: var(--ops-surface-2);
  color: var(--ops-text-1);
  font-size: 12px;
  cursor: pointer;
  transition: background 120ms ease;
}
.ov-btn:hover {
  background: var(--ops-muted);
}
.ov-btn:focus-visible {
  outline: 2px solid var(--ring);
  outline-offset: 2px;
}
.ov-del {
  display: inline-flex;
}
.ov-del :deep(button) {
  border-radius: 999px;
}
/* ---- 分页 ---- */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 14px;
}
.pager-info {
  font-size: 12px;
  color: var(--ops-text-3);
  font-variant-numeric: tabular-nums;
}
</style>
