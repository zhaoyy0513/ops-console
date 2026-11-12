<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Download, ExternalLink } from 'lucide-vue-next'
import { FileViewer } from '@file-viewer/vue3'
import '@file-viewer/vue3/dist/file-viewer3.css'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { isDarkTheme, useThemeStore } from '../../stores/theme'
import { contentUrl, fileExt, type KnowledgeDoc } from './api'

const props = defineProps<{
  show: boolean
  siteId: string
  doc: KnowledgeDoc | null
  onDownload: (doc: KnowledgeDoc) => void
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void }>()

const theme = useThemeStore()

/** 解析中：file-viewer 的重格式管线是 lazy async（PDF/Office 首次要拉 worker 与 wasm），
 *  在其 load-complete 之前盖一层转圈，避免用户对着空白区以为坏了 */
const parsing = ref(false)
/** 解析失败（格式不支持/文件损坏）：给下载兜底而不是空白 */
const failed = ref(false)

const url = computed(() =>
  props.doc ? contentUrl(props.siteId, props.doc.id) : '',
)
/** 只有 synth 深色，其余浅色——file-viewer 只认 light/dark */
const viewerTheme = computed(() => (isDarkTheme(theme.theme) ? 'dark' : 'light'))

/** HTML 静态页预览：file-viewer 的 text renderer 会禁用脚本（安全策略），
 *  导致依赖 JS 渲染的报告空白；这里改用 sandbox="allow-scripts" 的 srcdoc iframe，
 *  与 Page 的 sandbox 壳一致：脚本可跑，但 opaque origin 拿不到本域 cookie/storage。 */
const isHtml = computed(() => {
  if (!props.doc) return false
  const ext = fileExt(props.doc)
  return ext === 'html' || ext === 'htm' || (props.doc.mime ?? '').toLowerCase().includes('html')
})
const htmlSource = ref('')
const htmlLoading = ref(false)
const htmlError = ref('')

// 每次打开重置状态；关闭后卸载组件（v-if），file-viewer 会自行销毁渲染会话
let watchdog: ReturnType<typeof setTimeout> | null = null

function clearWatchdog() {
  if (watchdog) clearTimeout(watchdog)
  watchdog = null
}

watch(
  () => [props.show, props.doc?.id] as const,
  async ([show]) => {
    clearWatchdog()
    if (!show) {
      htmlSource.value = ''
      htmlError.value = ''
      htmlLoading.value = false
      return
    }
    parsing.value = true
    failed.value = false
    htmlError.value = ''

    if (isHtml.value && props.doc) {
      htmlLoading.value = true
      try {
        const res = await fetch(contentUrl(props.siteId, props.doc.id), { credentials: 'same-origin' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        htmlSource.value = await res.text()
      } catch (e) {
        htmlError.value = (e as Error).message
      } finally {
        htmlLoading.value = false
      }
      return
    }

    htmlSource.value = ''
    // 兜底：既没有 load-complete 也没有 error 时（worker 拉取失败等），20s 后收起转圈
    watchdog = setTimeout(() => {
      parsing.value = false
    }, 20_000)
  },
  { immediate: true },
)

onBeforeUnmount(clearWatchdog)

function onLoadStart() {
  parsing.value = true
}

function onLoadComplete() {
  clearWatchdog()
  parsing.value = false
}

/** file-viewer 的错误事件名是 error（不是 load-error）；渲染失败给下载兜底 */
function onViewerError() {
  clearWatchdog()
  parsing.value = false
  failed.value = true
}

function openInNewTab() {
  if (url.value) window.open(url.value, '_blank', 'noopener')
}

function download() {
  if (props.doc) props.onDownload(props.doc)
}
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="flex h-[88vh] w-[92vw] max-w-none flex-col overflow-hidden">
      <DialogHeader>
        <DialogTitle>{{ props.doc?.name ?? '' }}</DialogTitle>
      </DialogHeader>

      <div class="viewer-wrap min-h-0 flex-1">
        <!-- HTML：sandbox 允许脚本但隔离 origin，保证依赖 JS 的报告能渲染 -->
        <template v-if="isHtml">
          <iframe
            v-if="props.show && props.doc"
            :key="props.doc.id"
            class="html-frame"
            sandbox="allow-scripts"
            referrerpolicy="no-referrer"
            :srcdoc="htmlSource"
          />
          <div v-if="htmlLoading" class="viewer-mask">
            <span class="viewer-spinner" />
            <span class="text-sm text-muted-foreground">{{ $t('knowledge.parsing') }}</span>
          </div>
          <div v-else-if="htmlError" class="viewer-mask">
            <p class="text-sm text-muted-foreground">{{ htmlError }}</p>
            <Button variant="outline" size="sm" @click="openInNewTab">
              <ExternalLink />
              {{ $t('knowledge.openInNewTab') }}
            </Button>
          </div>
        </template>

        <!-- 非 HTML：file-viewer -->
        <template v-else>
          <!-- v-if 而非 v-show：关闭即卸载，file-viewer 会销毁渲染会话（PPT 图表等不留 DOM） -->
          <!-- 关键：content 端点 URL 不带扩展名，必须显式传 filename/type/size，
               否则 file-viewer 无法识别格式，会一律提示「不支持在线预览」 -->
          <file-viewer
            v-if="props.show && props.doc && url"
            :key="props.doc.id"
            :url="url"
            :filename="props.doc.filename"
            :type="props.doc.mime"
            :size="props.doc.size"
            :options="{ theme: viewerTheme, toolbar: { position: 'bottom-right' } }"
            style="height: 100%; width: 100%"
            @load-start="onLoadStart"
            @load-complete="onLoadComplete"
            @error="onViewerError"
          />

          <!-- 解析中 -->
          <div v-if="parsing && !failed" class="viewer-mask">
            <span class="viewer-spinner" />
            <span class="text-sm text-muted-foreground">{{ $t('knowledge.parsing') }}</span>
          </div>

          <!-- 解析失败兜底 -->
          <div v-else-if="failed" class="viewer-mask">
            <p class="text-sm text-muted-foreground">{{ $t('knowledge.parseFailed') }}</p>
            <Button variant="outline" size="sm" @click="openInNewTab">
              <ExternalLink />
              {{ $t('knowledge.openInNewTab') }}
            </Button>
          </div>
        </template>
      </div>

      <DialogFooter class="flex-row items-center justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" @click="download">
          <Download />
          {{ $t('knowledge.download') }}
        </Button>
        <Button variant="outline" size="sm" @click="openInNewTab">
          <ExternalLink />
          {{ $t('knowledge.openInNewTab') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.viewer-wrap {
  position: relative;
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  overflow: hidden;
  background: var(--ops-surface);
}
.html-frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}
.viewer-mask {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--ops-dialog);
  backdrop-filter: blur(4px);
}
.viewer-spinner {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--ops-border);
  border-top-color: var(--primary);
  animation: viewer-spin 0.8s linear infinite;
}
@keyframes viewer-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .viewer-spinner { animation-duration: 2.4s; }
}
</style>
