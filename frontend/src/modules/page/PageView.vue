<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Link2, Plus } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import TipCopy from '../../components/TipCopy.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { openHtmlInNewTab } from '../../utils/sandbox-open'
import { useSiteStore } from '../../stores/site'
import PageDialog from './PageDialog.vue'
import { pageApi, derivePageKind, type PageResource } from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const pages = ref<PageResource[]>([])
const loading = ref(false)

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
  try {
    await pageApi.remove(siteId, p.id)
    message.success(t('page.deleted'))
    await load()
  } catch (e) {
    message.error((e as Error).message)
    throw e
  }
}

/** 打开一律新标签：链接直开；HTML 文件经 sandbox 壳隔离
 *  （allow-scripts 可跑、opaque origin 拿不到本域 cookie/storage） */
function open(p: PageResource) {
  if (derivePageKind(p) === 'url' && p.url) {
    window.open(p.url, '_blank', 'noopener')
    return
  }
  if (p.html) openHtmlInNewTab(p.html)
}

/** 卡片聚光跟随：只写 CSS 变量，不进响应式状态、不触发重渲 */
function onCardMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--px', `${e.clientX - r.left}px`)
  el.style.setProperty('--py', `${e.clientY - r.top}px`)
}

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
          <!-- 悬停位移作用在 .card-lift 上；遮罩嵌在其内一起位移（删除确认弹窗已 Teleport 到 body，不受 transform 影响） -->
          <div class="page-card" @click="open(p)" @mousemove="onCardMove">
            <div class="card-lift">
              <div class="pc-head">
                <span class="pc-title">
                  <Link2 v-if="derivePageKind(p) === 'url'" class="pc-icon" />
                  <FileText v-else class="pc-icon" />
                  {{ p.name }}
                </span>
                <!-- 链接=紫（primary），HTML 文件=绿（success）：两类一眼可分 -->
                <Badge size="sm" :variant="derivePageKind(p) === 'url' ? 'default' : 'success'">
                  {{ kindLabel(p) }}
                </Badge>
              </div>
              <div class="pc-desc">{{ p.description }}</div>
              <div v-if="derivePageKind(p) === 'url' && p.url" class="pc-url">
                <tip-copy :text="p.url" :max="280" :copy="false" />
              </div>

              <!-- hover 遮罩放在位移层内：与卡片一起抬起，不再露出缝隙 -->
              <div class="card-overlay" @click.stop>
                <button type="button" class="ov-btn" @click="open(p)">{{ $t('page.open') }}</button>
                <button type="button" class="ov-btn" @click="startEdit(p)">{{ $t('page.edit') }}</button>
                <span class="ov-del">
                  <countdown-confirm :label="$t('page.del')" :target="p.name" :on-confirm="() => remove(p)" />
                </span>
              </div>
            </div>

          </div>
        </fade-content>
      </div>
      <empty-state v-else :title="$t('page.empty')" />
    </CardContent>
  </Card>

  <!-- 新建/编辑两用弹窗：站点只读、url/html 二选一、.html 上传 -->
  <PageDialog v-model:show="showEditor" :site-id="siteStore.currentSiteId ?? ''" :editing="editing" @saved="load" />
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
/* 卡片：视觉与位移都在 .card-lift；遮罩嵌在其内，随卡片一起抬起（不再露缝） */
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
  box-shadow: 0 12px 28px color-mix(in srgb, var(--ops-text-1) 16%, transparent);
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
/* 仅键盘聚焦（:focus-visible）显形：点开弹窗再关闭不会残留遮罩态 */
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
</style>
