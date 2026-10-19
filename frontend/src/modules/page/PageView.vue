<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NCard, NModal, NSpin, NTag, NIcon, useMessage } from 'naive-ui'
import { DocumentTextOutline, LinkOutline } from '@vicons/ionicons5'
import EmptyState from '../../components/EmptyState.vue'
import TabHelp from '../../components/TabHelp.vue'
import FadeContent from '../../components/bits/FadeContent.vue'
import TipCopy from '../../components/TipCopy.vue'
import { useSiteStore } from '../../stores/site'
import { pageApi, type PageResource } from './api'

const siteStore = useSiteStore()
const message = useMessage()

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

/** 跳转逻辑：URL 型新开标签页；HTML 型在站内 sandbox iframe 渲染 */
function open(p: PageResource) {
  if (p.kind === 'html') {
    active.value = p
    showHtml.value = true
    return
  }
  if (p.url) window.open(p.url, '_blank', 'noopener')
}

/** 卡片聚光跟随：只写 CSS 变量，不进响应式状态、不触发重渲 */
function onCardMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  el.style.setProperty('--px', `${e.clientX - r.left}px`)
  el.style.setProperty('--py', `${e.clientY - r.top}px`)
}

const activeSrcDoc = computed(() => active.value?.html ?? '')

</script>

<template>
  <n-card size="small">
    <template #header-extra>
      <span style="color: var(--ops-text-3); font-size: 12px">{{ $t('page.hintShort') }}</span>
      <tab-help topic="page" />
    </template>
    <n-spin :show="loading">
      <div v-if="pages.length" class="page-grid">
        <fade-content v-for="(p, i) in pages" :key="p.id" :delay="i * 60" class="page-fade">
          <div class="page-card" @click="open(p)" @mousemove="onCardMove">
            <div class="pc-head">
              <span class="pc-title">{{ p.name }}</span>
              <span class="pc-kind">
                <n-icon :size="13" :component="p.kind === 'html' ? DocumentTextOutline : LinkOutline" />
                <n-tag size="small" round :bordered="false" :type="p.kind === 'html' ? 'default' : 'info'">
                  {{ p.kind === 'html' ? $t('page.kindHtml') : $t('page.kindUrl') }}
                </n-tag>
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
    </n-spin>
  </n-card>

  <!-- HTML 型页面站内预览：sandbox 隔离（allow-scripts 但不 allow-same-origin，
       脚本可运行却拿不到本域 cookie/storage——内部工具嵌入不受信页面的安全底线）。
       缩放淡入进场：naive 内置 zoomed-out-transition，借 Bits「缩放进容器」的体感 -->
  <n-modal
    :mask-closable="false"
    :close-on-esc="false"
    v-model:show="showHtml"
    preset="card"
    :title="active?.name ?? ''"
    transition="scale"
    style="width: 92vw; max-height: 88vh; display: flex; flex-direction: column"
  >
    <iframe
      v-if="active"
      class="html-frame"
      sandbox="allow-scripts"
      :srcdoc="activeSrcDoc"
      :title="active.name"
    />
    <template #footer>
      <div class="frame-foot">
        <span class="frame-note">{{ $t('page.frameNote') }}</span>
      </div>
    </template>
  </n-modal>
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
  width: 100%;
  height: 72vh;
  border: 1px solid var(--ops-border);
  border-radius: 4px;
  background: var(--ops-surface);
}
.frame-foot {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}
.frame-note {
  color: var(--ops-text-3);
  font-size: 12px;
}
</style>
