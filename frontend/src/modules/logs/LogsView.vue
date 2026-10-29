<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  Loader2, Plus, RefreshCw, Search, Settings2,
} from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { message } from '@/lib/message'
import EmptyState from '../../components/EmptyState.vue'
import OpsSwitch from '../../components/OpsSwitch.vue'
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { useSiteStore } from '../../stores/site'
import { logsApi, type LogFile, type LogMode, type LogReadResult, type LogSource } from './api'

const { t } = useI18n()
const siteStore = useSiteStore()

const LINES = 200
const PREV_STEP = 64 * 1024 // 上一页按字节回退（行宽不可预知，允许少量重叠）
const FOLLOW_MS = 3000
const MAX_FOLLOW_LINES = 4000 // 长时间跟随只保留最近 4000 行

const sources = ref<LogSource[]>([])
const sourceId = ref<string | null>(null)
// 目录级：选中日志源后先列文件，打开某个文件才读内容
const files = ref<LogFile[]>([])
const filesLoading = ref(false)
const filesError = ref<string | null>(null)
const filesTruncated = ref(false)
const currentFile = ref<string | null>(null)
const content = ref('')
const loading = ref(false)
const polling = ref(false)
const follow = ref(false)
const showLineNumbers = ref(true)
const searchKw = ref('')
const errorCode = ref<string | null>(null)
const errorText = ref('')
const startOffset = ref(0)
const nextOffset = ref(0)
const fileSize = ref(0)
const eof = ref(true)
const truncated = ref(false)
const lastInode = ref<string | null>(null)
const logBox = ref<HTMLElement | null>(null)

interface Draft {
  id: string | null
  label: string
  path: string
}
const showManage = ref(false)
const drafts = ref<Draft[]>([])
const saving = ref(false)

const currentSource = computed(() => sources.value.find((s) => s.id === sourceId.value) ?? null)
const canPrev = computed(() => !!sourceId.value && startOffset.value > 0)
const canNext = computed(() => !!sourceId.value && !eof.value)

/** 列目录的错误码（与读取分开：多了 NOT_A_DIR） */
const FILE_ERROR_KEYS: Record<string, string> = {
  NO_PERMISSION: 'logs.noPermission',
  NOT_FOUND: 'logs.notFound',
  NOT_A_DIR: 'logs.notADir',
  NO_SERVER: 'logs.noServer',
  BAD_RESPONSE: 'logs.readFailed',
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const ERROR_KEYS: Record<string, string> = {
  NO_PERMISSION: 'logs.noPermission',
  NOT_FOUND: 'logs.notFound',
  NOT_A_FILE: 'logs.notAFile',
  STAT_FAILED: 'logs.statFailed',
  NO_SERVER: 'logs.noServer',
  BAD_RESPONSE: 'logs.readFailed',
}

const errorMessage = computed(() => {
  if (!errorCode.value) return ''
  return t(ERROR_KEYS[errorCode.value] ?? 'logs.readFailed')
})
const errorHint = computed(() => {
  if (errorCode.value === 'NO_PERMISSION') return t('logs.noPermissionHint')
  if (errorCode.value === 'NO_SERVER') return t('logs.noServerHint')
  return ''
})

const displayContent = computed(() => {
  if (!showLineNumbers.value) return content.value
  const rows = content.value.split('\n')
  if (rows.length && rows[rows.length - 1] === '') rows.pop()
  return rows.map((line, i) => `${String(i + 1).padStart(5, ' ')}  ${line}`).join('\n')
})

function clearError() {
  errorCode.value = null
  errorText.value = ''
}

function setError(r: LogReadResult) {
  errorCode.value = r.error_code ?? 'READ_FAILED'
  errorText.value = r.error ?? ''
}

function isNearBottom(): boolean {
  const el = logBox.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

async function scrollToBottom() {
  await nextTick()
  const el = logBox.value
  if (el) el.scrollTop = el.scrollHeight
}

/** 统一读取入口：silent=true 时不动全局 loading（跟随轮询不闪按钮）。 */
async function fetchRead(
  mode: LogMode,
  opts: { offset?: number; kw?: string; lines?: number } = {},
  silent = false,
): Promise<LogReadResult | null> {
  const siteId = siteStore.currentSiteId
  const id = sourceId.value
  if (!siteId || !id) return null
  if (!silent) loading.value = true
  try {
    return await logsApi.read(siteId, id, {
      file: currentFile.value ?? '',
      mode, offset: opts.offset, kw: opts.kw, lines: opts.lines ?? LINES,
    })
  } catch (e) {
    message.error((e as Error).message)
    return null
  } finally {
    if (!silent) loading.value = false
  }
}

/** 成功窗口统一更新游标；probe 失败只记错误，不覆盖已加载内容。 */
function applyWindow(r: LogReadResult, checkRotation = true): boolean {
  if (r.error_code) {
    setError(r)
    return false
  }
  if (checkRotation) {
    // 轮转：inode 变化，或文件比当前游标还短（copytruncate 截断后 inode 不变）
    const rotated =
      (!!lastInode.value && !!r.inode && r.inode !== lastInode.value) ||
      r.size < nextOffset.value
    if (rotated) {
      lastInode.value = null // 先清掉，避免 loadTail 里再次判定轮转
      message.info(t('logs.rotated'))
      void loadTail()
      return false
    }
  }
  clearError()
  startOffset.value = r.start_offset
  nextOffset.value = r.next_offset
  fileSize.value = r.size
  eof.value = r.eof
  truncated.value = r.truncated
  lastInode.value = r.inode || lastInode.value
  return true
}

async function loadTail() {
  const r = await fetchRead('tail')
  if (!r || !applyWindow(r, false)) return
  content.value = r.content
  lastInode.value = r.inode || null
  await scrollToBottom()
}

async function loadHead() {
  follow.value = false // 手动定位后从新游标跟随会重复追加，交给用户重新打开
  const r = await fetchRead('head')
  if (!r || !applyWindow(r)) return
  content.value = r.content
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = 0
}

async function prevPage() {
  follow.value = false
  const r = await fetchRead('offset', { offset: Math.max(0, startOffset.value - PREV_STEP) })
  if (!r || !applyWindow(r)) return
  content.value = r.content
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = 0
}

async function nextPage() {
  follow.value = false
  const r = await fetchRead('offset', { offset: nextOffset.value })
  if (!r || !applyWindow(r)) return
  content.value = r.content
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = 0
}

async function runSearch() {
  const kw = searchKw.value.trim()
  if (!kw) {
    message.warning(t('logs.needKeyword'))
    return
  }
  follow.value = false // 搜索结果是历史窗口，继续跟随会把新行追加到结果里
  const r = await fetchRead('search', { kw })
  if (!r || !applyWindow(r)) return
  content.value = r.content
  await nextTick()
  if (logBox.value) logBox.value.scrollTop = 0
}

/** 跟随增量：从 next_offset 继续；前端限制保留行数，避免长时间开着吃内存。 */
function appendContent(chunk: string) {
  const merged = content.value + chunk
  const rows = merged.split('\n')
  if (rows.length <= MAX_FOLLOW_LINES) {
    content.value = merged
    return
  }
  const removed = rows.slice(0, rows.length - MAX_FOLLOW_LINES).join('\n') + '\n'
  startOffset.value += new TextEncoder().encode(removed).length
  content.value = rows.slice(-MAX_FOLLOW_LINES).join('\n')
}

async function pollFollow() {
  if (!sourceId.value || polling.value) return
  polling.value = true
  try {
    // 跟随单次多取（最多 1000 行，仍受后端 256KB 上限），忙日志不至于永远追不上
    const r = await fetchRead('offset', { offset: nextOffset.value, lines: 1000 }, true)
    if (!r) return
    // applyWindow 内做轮转检测：变化时重置到末尾并提示
    if (!applyWindow(r)) return
    if (r.content) {
      const stick = isNearBottom()
      appendContent(r.content)
      if (stick) await scrollToBottom()
    }
  } finally {
    polling.value = false
  }
}

// ---- 跟随定时器：interval + visibilitychange 暂停 + 卸载清理 ----
let followTimer: number | null = null

function startFollowTimer() {
  if (followTimer == null) followTimer = window.setInterval(pollFollow, FOLLOW_MS)
}
function stopFollowTimer() {
  if (followTimer != null) {
    clearInterval(followTimer)
    followTimer = null
  }
}
function onVisibility() {
  if (document.hidden) stopFollowTimer()
  else if (follow.value) startFollowTimer()
}
watch(follow, (v) => {
  if (v) {
    void pollFollow()
    startFollowTimer()
  } else {
    stopFollowTimer()
  }
})

function resetView() {
  content.value = ''
  startOffset.value = 0
  nextOffset.value = 0
  fileSize.value = 0
  eof.value = true
  truncated.value = false
  lastInode.value = null
  clearError()
}

/** 列出当前日志源目录下的文件（只 stat，不读内容——100MB 文件也只是元数据） */
async function loadFiles() {
  const siteId = siteStore.currentSiteId
  const id = sourceId.value
  filesError.value = null
  filesTruncated.value = false
  if (!siteId || !id) {
    files.value = []
    return
  }
  filesLoading.value = true
  try {
    const r = await logsApi.listFiles(siteId, id)
    files.value = r.files ?? []
    filesTruncated.value = !!r.truncated
    if (r.error_code) filesError.value = r.error_code
  } catch (e) {
    filesError.value = 'READ_FAILED'
    message.error((e as Error).message)
  } finally {
    filesLoading.value = false
  }
}

/** 打开某个文件：切到阅读视图并读尾部 */
async function openFile(name: string) {
  currentFile.value = name
  resetView()
  await loadTail()
}

/** 回到文件列表（停止跟随，避免继续读已关闭的文件） */
function closeFile() {
  follow.value = false
  currentFile.value = null
  resetView()
}

async function reloadCurrent() {
  resetView()
  currentFile.value = null
  await loadFiles()
}

async function loadSources() {
  const siteId = siteStore.currentSiteId
  if (!siteId) {
    sources.value = []
    sourceId.value = null
    resetView()
    return
  }
  try {
    sources.value = await logsApi.list(siteId)
  } catch (e) {
    message.error((e as Error).message)
    return
  }
  if (!sources.value.some((s) => s.id === sourceId.value)) {
    sourceId.value = sources.value[0]?.id ?? null
  }
  await reloadCurrent()
}

function onSourceChange(v: unknown) {
  if (typeof v === 'string' && v && v !== sourceId.value) {
    sourceId.value = v
    void reloadCurrent()
  }
}

function openManage() {
  drafts.value = sources.value.map((s) => ({ id: s.id, label: s.label, path: s.path }))
  showManage.value = true
}

function addDraft() {
  drafts.value.push({ id: null, label: '', path: '' })
}

async function saveDraft(d: Draft) {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  const label = d.label.trim()
  const path = d.path.trim()
  if (!label) {
    message.warning(t('logs.needLabel'))
    return
  }
  if (!path.startsWith('/')) {
    message.warning(t('logs.pathAbsolute'))
    return
  }
  saving.value = true
  try {
    if (d.id) await logsApi.update(siteId, d.id, { label, path })
    else await logsApi.create(siteId, { label, path })
    message.success(t('logs.saved'))
    showManage.value = false
    await loadSources()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function removeDraft(d: Draft) {
  const siteId = siteStore.currentSiteId
  if (!siteId || !d.id) return
  try {
    await logsApi.remove(siteId, d.id)
    message.success(t('logs.deleted'))
    await loadSources()
    drafts.value = sources.value.map((s) => ({ id: s.id, label: s.label, path: s.path }))
  } catch (e) {
    message.error((e as Error).message)
    throw e // 让 CountdownConfirm 保持弹窗可重试
  }
}

watch(() => siteStore.currentSiteId, () => {
  sourceId.value = null
  void loadSources()
})

onMounted(() => {
  void loadSources()
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  stopFollowTimer()
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>{{ $t('logs.title') }}</CardTitle>
      <template #action>
        <Button variant="outline" size="sm" :disabled="!siteStore.currentSiteId" @click="openManage">
          <Settings2 />
          {{ $t('logs.manage') }}
        </Button>
      </template>
    </CardHeader>
    <CardContent class="space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <Select :model-value="sourceId" @update:model-value="onSourceChange">
          <SelectTrigger class="w-[220px]" :placeholder="$t('logs.selectSource')" />
          <SelectContent>
            <SelectItem v-for="s in sources" :key="s.id" :value="s.id">{{ s.label }}</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" :disabled="!sourceId || loading" @click="loadTail">
          <RefreshCw />
          {{ $t('common.refresh') }}
        </Button>
        <template v-if="currentFile">
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
            <OpsSwitch :value="follow" :disabled="!sourceId" @update:value="follow = $event" />
            {{ $t('logs.follow') }}
          </label>
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
            <OpsSwitch :value="showLineNumbers" @update:value="showLineNumbers = $event" />
            {{ $t('logs.lineNumbers') }}
          </label>
        </template>
        <span class="ml-auto inline-flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
          <Loader2 v-if="loading || filesLoading" class="size-3.5 shrink-0 animate-spin" />
          <span v-if="currentSource" class="truncate font-mono">
            {{ currentSource.path }}<template v-if="currentFile">/{{ currentFile }}</template>
          </span>
        </span>
      </div>

      <div v-if="!sources.length" class="py-10">
        <EmptyState :title="$t('logs.noSources')" :desc="$t('logs.noSourcesHint')">
          <Button size="sm" class="mt-2" :disabled="!siteStore.currentSiteId" @click="openManage">
            <Plus />
            {{ $t('logs.manage') }}
          </Button>
        </EmptyState>
      </div>

      <!-- 未打开文件：列出目录下的日志文件（只 stat，不读内容） -->
      <template v-else-if="!currentFile">
        <div v-if="filesError" class="log-error">
          <AlertTriangle class="size-4 shrink-0" />
          <div class="min-w-0">
            <div>{{ $t(FILE_ERROR_KEYS[filesError] ?? 'logs.readFailed') }}</div>
            <div v-if="filesError === 'NO_PERMISSION'" class="log-error-hint">{{ $t('logs.noPermissionHint') }}</div>
            <div v-if="filesError === 'NO_SERVER'" class="log-error-hint">{{ $t('logs.noServerHint') }}</div>
            <div v-if="filesError === 'NOT_A_DIR'" class="log-error-hint">{{ $t('logs.notADir') }}</div>
          </div>
        </div>

        <div v-if="filesLoading" class="flex justify-center py-10">
          <Loader2 class="size-5 animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="files.length" class="file-table">
          <div class="file-row file-head">
            <span>{{ $t('logs.colName') }}</span>
            <span>{{ $t('logs.colSize') }}</span>
            <span>{{ $t('logs.colMtime') }}</span>
            <span />
          </div>
          <div v-for="f in files" :key="f.name" class="file-row" @dblclick="openFile(f.name)">
            <span class="truncate font-mono" :title="f.name">{{ f.name }}</span>
            <span class="num">{{ fmtSize(f.size) }}</span>
            <span class="num">{{ fmtTime(f.mtime) }}</span>
            <Button size="sm" variant="outline" @click="openFile(f.name)">{{ $t('logs.open') }}</Button>
          </div>
        </div>
        <div v-else-if="!filesError" class="py-10">
          <EmptyState :title="$t('logs.noFiles')" :desc="$t('logs.noFilesHint')" />
        </div>
        <div v-if="filesTruncated" class="log-warn">{{ $t('logs.filesTruncated') }}</div>
      </template>

      <!-- 已打开文件：阅读视图 -->
      <template v-else>
        <div class="flex items-center gap-2">
          <Button variant="outline" size="sm" @click="closeFile">
            <ChevronLeft />
            {{ $t('logs.backToList') }}
          </Button>
          <span class="truncate font-mono text-xs text-muted-foreground">{{ currentFile }}</span>
        </div>

        <div v-if="errorMessage" class="log-error">
          <AlertTriangle class="size-4 shrink-0" />
          <div class="min-w-0">
            <div>{{ errorMessage }}</div>
            <div v-if="errorHint" class="log-error-hint">{{ errorHint }}</div>
            <div v-if="errorText && errorText !== errorCode" class="log-error-hint font-mono">{{ errorText }}</div>
          </div>
        </div>

        <div v-if="truncated" class="log-warn">{{ $t('logs.truncated') }}</div>

        <div ref="logBox" class="log-box">
          <pre v-if="content" class="log-pre">{{ displayContent }}</pre>
          <div v-else class="log-empty">{{ $t('logs.empty') }}</div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" :disabled="!sourceId || loading" @click="loadHead">
            <ChevronsLeft />
            {{ $t('logs.toHead') }}
          </Button>
          <Button variant="outline" size="sm" :disabled="!canPrev || loading" @click="prevPage">
            <ChevronLeft />
            {{ $t('logs.prevPage') }}
          </Button>
          <Button variant="outline" size="sm" :disabled="!canNext || loading" @click="nextPage">
            <ChevronRight />
            {{ $t('logs.nextPage') }}
          </Button>
          <Button variant="outline" size="sm" :disabled="!sourceId || loading" @click="loadTail">
            <ChevronsRight />
            {{ $t('logs.toTail') }}
          </Button>
          <span class="ml-auto text-xs text-muted-foreground">
            {{ $t('logs.rangeInfo', { start: startOffset, next: nextOffset, size: fileSize }) }}
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Input
            v-model="searchKw"
            class="w-[240px]"
            :placeholder="$t('logs.searchPh')"
            @keyup.enter="runSearch"
          />
          <Button variant="outline" size="sm" :disabled="!sourceId || loading" @click="runSearch">
            <Search />
            {{ $t('logs.search') }}
          </Button>
          <span class="text-xs text-muted-foreground">{{ $t('logs.searchWindowHint') }}</span>
        </div>
      </template>
    </CardContent>
  </Card>

  <Dialog :open="showManage" @update:open="(v: boolean) => (showManage = v)">
    <DialogContent class="w-[760px] max-w-[94vw]">
      <DialogHeader>
        <DialogTitle>{{ $t('logs.manageTitle') }}</DialogTitle>
      </DialogHeader>
      <div class="grid gap-2">
        <div v-for="(d, i) in drafts" :key="d.id ?? `new-${i}`" class="draft-row">
          <Input v-model="d.label" :placeholder="$t('logs.labelPh')" />
          <Input v-model="d.path" class="font-mono" :placeholder="$t('logs.pathPh')" />
          <Button size="sm" :disabled="saving" @click="saveDraft(d)">{{ $t('common.save') }}</Button>
          <CountdownConfirm
            v-if="d.id"
            :label="$t('common.delete')"
            :target="d.label || d.path"
            :on-confirm="() => removeDraft(d)"
          />
          <Button v-else variant="ghost" size="sm" @click="drafts.splice(i, 1)">
            {{ $t('common.cancel') }}
          </Button>
        </div>
      </div>
      <div class="flex items-center justify-between pt-2">
        <Button variant="outline" size="sm" @click="addDraft">
          <Plus />
          {{ $t('logs.addSource') }}
        </Button>
        <Button variant="outline" size="sm" @click="showManage = false">{{ $t('common.close') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.log-box {
  height: 56vh;
  min-height: 240px;
  overflow: auto;
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  background: var(--ops-surface-2);
}
.log-pre {
  margin: 0;
  padding: 10px 12px;
  font-family: var(--ops-font-mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre;
  tab-size: 4;
  color: var(--ops-text-1);
}
.log-empty {
  padding: 48px 0;
  text-align: center;
  font-size: 12px;
  color: var(--ops-text-3);
}
.log-error {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--destructive) 40%, transparent);
  border-radius: var(--ops-radius-m);
  background: color-mix(in srgb, var(--destructive) 8%, transparent);
  color: var(--destructive);
  font-size: 12px;
}
.log-error-hint {
  margin-top: 2px;
  color: var(--ops-text-2);
}
.log-warn {
  font-size: 12px;
  color: var(--ops-warning);
}
.file-table {
  border: 1px solid var(--ops-border);
  border-radius: var(--ops-radius-m);
  overflow: hidden;
  max-height: 56vh;
  overflow-y: auto;
}
.file-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 100px 150px 80px;
  gap: 12px;
  align-items: center;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid var(--ops-border);
}
.file-row:last-child { border-bottom: none; }
.file-row:not(.file-head):hover { background: var(--ops-surface-2); }
.file-head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--ops-surface-2);
  font-weight: 600;
  color: var(--ops-text-2);
}
.file-row .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--ops-text-2);
}
.draft-row {
  display: grid;
  grid-template-columns: 1fr 2fr auto auto;
  gap: 8px;
  align-items: center;
}
</style>
