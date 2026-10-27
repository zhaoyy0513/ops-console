<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Expand, LoaderCircle, Shrink } from 'lucide-vue-next'
import { message } from '@/lib/message'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogBody,
  AlertDialogCancel,
  AlertDialogContent,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useSiteStore } from '../../stores/site'
import api from '../../api'
import OpsSwitch from '../../components/OpsSwitch.vue'
import EmptyState from '../../components/EmptyState.vue'
import SortTh from '../../components/SortTh.vue'
import ClickSpark from '../../components/bits/ClickSpark.vue'
import { useTableSort } from '../../composables/useTableSort'
import { sshApi, type SshScript } from './api'

const siteStore = useSiteStore()
const { t } = useI18n()

const scripts = ref<SshScript[]>([])
const loading = ref(false)

// 脚本表当前页排序（名称/cron；空 cron 恒末尾）
const {
  sortKey: sSortKey,
  sortDir: sSortDir,
  sortedRows: sortedScripts,
  toggleSort: toggleScriptSort,
} = useTableSort<SshScript>(scripts, (s, k) => (s as unknown as Record<string, unknown>)[k])

// 编辑弹窗状态
const editShow = ref(false)
const editingId = ref<string | null>(null)
const form = ref<{
  name: string
  server_id: string | null
  content: string
  cron: string
  sched_enabled: boolean
}>({
  name: '',
  server_id: null,
  content: '',
  cron: '',
  sched_enabled: false,
})

/** 是否定时脚本：由 cron 输入框是否有内容决定 */
const isCron = computed({
  get: () => !!form.value.cron.trim(),
  set: (v: boolean) => {
    // 打开时必须填入默认值——getter 由 cron 是否非空决定，置空字符串会让开关弹回
    form.value.cron = v ? '0 2 * * *' : ''
  },
})

const cronTesting = ref(false)
const cronNextRuns = ref<string[]>([])
const cronTzLabel = ref('')
const cronInvalid = ref(false)

async function testCron() {
  cronNextRuns.value = []
  cronTzLabel.value = ''
  if (!form.value.cron.trim()) {
    cronInvalid.value = false
    return
  }
  cronTesting.value = true
  try {
    const r = await api.post('/ssh/validate-cron', { cron: form.value.cron })
    cronNextRuns.value = (r as any).next_runs
    cronTzLabel.value = (r as any).tz_label ?? ''
    cronInvalid.value = false
  } catch (e) {
    cronNextRuns.value = []
    cronInvalid.value = true
  } finally {
    cronTesting.value = false
  }
}

async function toggleSched(item: SshScript, v: boolean) {
  try {
    const upd = await sshApi.update(siteStore.currentSiteId, item.id, { sched_enabled: v })
    item.sched_enabled = (upd as any).sched_enabled
  } catch (e) {
    message.error((e as Error).message)
  }
}

// Server 候选（绑定执行目标 + 名称联动候选）
const servers = ref<Array<{ label: string; value: string }>>([])

async function loadServers() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'servers')
    servers.value = list.map((s) => ({ label: s.name, value: s.id }))
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  loading.value = true
  try {
    scripts.value = await sshApi.list(siteId)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

/** 编辑弹窗内的测试：直接执行表单内容（run-adhoc），不创建、不保存脚本 */
const testing = ref(false)
async function testScript() {
  if (!siteStore.currentSiteId) return
  if (!form.value.server_id) {
    message.warning(t('ssh.serverRequired'))
    return
  }
  if (!form.value.content.trim()) {
    message.warning(t('ssh.contentRequired'))
    return
  }
  testing.value = true
  try {
    // 先做风险预检：safe 直接开执行弹窗跑；WARN 先弹确认框（用户确认后才开
    // 执行弹窗——曾因先开弹窗后确认，警告与执行弹窗同时出现，逻辑混乱）；
    // BLOCK 直接报错，什么弹窗都不开
    const res = await sshApi.assessRisk(form.value.content)
    if (res.level === 'block') {
      message.error(t('ssh.riskBlocked', { patterns: res.patterns.join('、') }))
      return
    }
    runTarget.value = {
      id: '',
      name: form.value.name.trim() || t('ssh.unsaved'),
      server_id: form.value.server_id,
      content: form.value.content,
      enabled: true,
    }
    if (res.level === 'warn') {
      riskConfirm.value = { patterns: res.patterns, openConsoleAfter: true }
      return
    }
    runShow.value = true
    startRun(false)
  } catch (e) {
    message.warning(t('ssh.assessFailed', { msg: (e as Error).message }))
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  loadServers()
  load()
})
watch(() => siteStore.currentSiteId, () => {
  scripts.value = []
  loadServers()
  load()
})

const serverName = computed(
  () => (id: string) => servers.value.find((s) => s.value === id)?.label ?? id,
)

function resetCronFeedback() {
  cronNextRuns.value = []
  cronTzLabel.value = ''
  cronInvalid.value = false
}

function openCreate() {
  editingId.value = null
  resetCronFeedback()
  form.value = { name: '', server_id: servers.value[0]?.value ?? null, content: '', cron: '', sched_enabled: false }
  editShow.value = true
}

function openEdit(item: SshScript) {
  editingId.value = item.id
  resetCronFeedback()
  form.value = {
    name: item.name,
    server_id: item.server_id,
    content: item.content,
    cron: item.cron ?? '',
    sched_enabled: !!item.sched_enabled,
  }
  editShow.value = true
}

async function save() {
  if (!siteStore.currentSiteId) return
  if (!form.value.name.trim()) {
    message.warning(t('ssh.nameRequired'))
    return
  }
  if (!form.value.server_id) {
    message.warning(t('ssh.serverRequired'))
    return
  }
  if (!form.value.content.trim()) {
    message.warning(t('ssh.contentRequired'))
    return
  }
  try {
    if (editingId.value) {
      await sshApi.update(siteStore.currentSiteId, editingId.value, { ...form.value, server_id: form.value.server_id ?? '' })
    } else {
      await sshApi.create(siteStore.currentSiteId, { ...form.value, server_id: form.value.server_id ?? '' })
    }
    message.success(t('ssh.saved'))
    editShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function remove(item: SshScript) {
  if (!siteStore.currentSiteId) return
  await sshApi.remove(siteStore.currentSiteId, item.id)
  message.success(t('ssh.deleted'))
  await load()
}

/** 删除确认弹窗（替代 NPopconfirm）：行内按钮只置目标，弹窗确认才执行 */
const removeTarget = ref<SshScript | null>(null)

/** 弹窗不响应 Esc / 点遮罩关闭（对齐原 mask-closable=false / close-on-esc=false） */
function blockDismiss(e: Event) {
  e.preventDefault()
}

// ---------- 执行（确认 + 黑色 console，可全屏） ----------
const runShow = ref(false)
const runFullscreen = ref(false)
const runTarget = ref<SshScript | null>(null)
const running = ref(false)
const runOutput = ref('')
const runTimedOut = ref(false)
const consoleEl = ref<HTMLElement | null>(null)
let runAbort: (() => void) | null = null

/** ANSI 转义剥离：颜色等控制序列原样追加会显示为乱码/方块。 */
function stripAnsi(s: string): string {
  return s.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '').replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, '')
}

/** 帧分隔：实时刷新命令（docker stats 等）每次重绘以 [H/[2J 开头，
 *  将其替换为带时间戳的分隔行——块与块之间一目了然，也能看出刷新节奏。 */
function frameSeparate(s: string): string {
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  return s.replace(/\x1b\[(?:H|2J)/g, `\n──── ${ts} ────\n`)
}

/** 追加输出并跟随滚动：贴底时自动滚到最新；用户向上翻阅（离底 >48px）则暂停跟随 */
function appendOut(s: string) {
  const el = consoleEl.value
  const stick = el ? el.scrollHeight - el.scrollTop - el.clientHeight < 48 : true
  runOutput.value += stripAnsi(s)
  if (stick && el) nextTick(() => { el.scrollTop = el.scrollHeight })
}

function stopRun() {
  runAbort?.() // 断开 SSE -> 后端 finally kill 远端进程，绝不遗留
  runAbort = null
  running.value = false
}

watch(runShow, (v) => { if (!v) stopRun() })
onBeforeUnmount(stopRun)

function askRun(item: SshScript) {
  runTarget.value = item
  runOutput.value = ''
  runTimedOut.value = false
  runShow.value = true
}

function backToEdit() {
  stopRun() // 回编辑即终止远端进程（与关闭窗口同语义，不留孤儿）
  runShow.value = false
  // 测试流（id 为空）：编辑弹窗仍开着，无需回填；表格执行流才回填表单
  if (runTarget.value?.id) {
    editingId.value = runTarget.value.id
    form.value = {
      name: runTarget.value.name,
      server_id: runTarget.value.server_id,
      content: runTarget.value.content,
      cron: runTarget.value.cron ?? '',
      sched_enabled: !!runTarget.value.sched_enabled,
    }
    editShow.value = true
  }
}

/** 风险预检：BLOCK 直接拒绝；WARN 弹确认框，用户确认后带 confirm_risk 重跑。
 *  后端在执行时仍兜底校验（前端预检只是 UX，可被绕过）。 */
const riskConfirm = ref<{ patterns: string[]; openConsoleAfter?: boolean } | null>(null)

async function assessAndRun() {
  const item = runTarget.value
  if (!item || !siteStore.currentSiteId) return
  const content = item.id ? '' : item.content
  // 表格流（按 id 执行已保存脚本）：内容在库里，预检取脚本内容
  const text = content || item.content || ''
  try {
    if (text.trim()) {
      const res = await sshApi.assessRisk(text)
      if (res.level === 'block') {
        message.error(t('ssh.riskBlocked', { patterns: res.patterns.join('、') }))
        running.value = false
        return
      }
      if (res.level === 'warn') {
        riskConfirm.value = { patterns: res.patterns }
        return // 等用户确认后 riskConfirmRun() 继续
      }
    }
  } catch (e) {
    // 预检接口失败必须可见（不能静默放行装作没问题）；执行仍由后端兜底校验
    message.warning(t('ssh.assessFailed', { msg: (e as Error).message }))
  }
  riskConfirm.value = null
  startRun(false)
}

/** 用户确认风险后的执行 */
function riskConfirmRun() {
  const openConsole = riskConfirm.value?.openConsoleAfter ?? false
  riskConfirm.value = null
  if (openConsole) runShow.value = true // 测试入口：确认后才开执行弹窗
  startRun(true)
}

/** 流式执行（测试流 id 为空时跑表单内容；表格流按 id）。
 *  每次执行 console 全新开始（互不影响）；输出实时追加并跟随滚动。 */
function startRun(confirmRisk: boolean) {
  const item = runTarget.value
  if (!item || !siteStore.currentSiteId) return
  stopRun()
  runOutput.value = '' // 每次执行独立，不带上一次的内容
  runTimedOut.value = false
  running.value = true
  let sawStderr = false
  const onChunk = (kind: string, data: string) => {
    if (kind === 'stdout') {
      let out = frameSeparate(data)
      // 首帧前不加分隔行（第一块数据前无需分隔）
      if (!runOutput.value) out = out.replace(/^\n──── [0-9:]{8} ────\n/, '')
      appendOut(out)
    }
    else if (kind === 'stderr') {
      // stderr 实时上屏（top 等无终端命令秒退时报错立即可见，不再攒到最后）
      appendOut((sawStderr ? '' : '[stderr] ') + data)
      sawStderr = true
    }
    else if (kind === 'meta') {
      try {
        const m = JSON.parse(data)
        runTimedOut.value = !!m.timed_out
        if (m.timed_out) message.warning(t('ssh.timeoutWarn'))
      } catch { /* 忽略 */ }
      running.value = false
      // 全程无输出的执行（如 .12 上裸 top 静默退出）：结论落进 console 持久显示，
      // 否则会回落到"点击执行"占位、把此前的无输出提示顶掉
      if (!runOutput.value) appendOut(t('ssh.noOutputEnd'))
    } else if (kind === 'error') {
      appendOut(t('ssh.runFailed', { msg: data }))
      running.value = false
    }
  }
  runAbort = item.id
    ? sshApi.runStream(siteStore.currentSiteId, item.id, onChunk, confirmRisk)
    : sshApi.runAdhocStream(
        siteStore.currentSiteId, form.value.server_id ?? '', form.value.content, onChunk, confirmRisk)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <Card>
      <CardHeader>
        <div class="flex flex-wrap items-center gap-3">
          <CardTitle>{{ $t('ssh.title') }}</CardTitle>
          <span class="hidden text-xs text-muted-foreground md:inline">{{ $t('ssh.hintShort') }}</span>
        </div>
        <template #action>
          <div class="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" :disabled="loading" @click="load">
              <LoaderCircle v-if="loading" class="animate-spin" />
              {{ $t('common.refresh') }}
            </Button>
            <Button size="sm" @click="openCreate">{{ $t('ssh.newScript') }}</Button>
          </div>
        </template>
      </CardHeader>
      <CardContent>
        <!-- 窄窗口时表格内部横向滚动，不撑破页面 -->
        <div class="overflow-x-auto">
          <table class="w-full table-fixed border-collapse text-sm">
          <thead>
            <tr class="border-b border-border">
              <sort-th class="px-2.5 py-2 text-left font-medium text-muted-foreground" :label="$t('ssh.colName')" :active="sSortKey === 'name'" :dir="sSortKey === 'name' ? sSortDir : null" @sort="toggleScriptSort('name')" />
              <th class="px-2.5 py-2 text-left font-medium text-muted-foreground" style="width: 22%">{{ $t('ssh.colServer') }}</th>
              <sort-th class="px-2.5 py-2 text-left font-medium text-muted-foreground" style="width: 100px" :label="$t('ssh.colCron')" :active="sSortKey === 'cron'" :dir="sSortKey === 'cron' ? sSortDir : null" @sort="toggleScriptSort('cron')" />
              <th class="px-2.5 py-2 text-left font-medium text-muted-foreground" style="width: 70px">{{ $t('ssh.colSched') }}</th>
              <th class="px-2.5 py-2 text-left font-medium text-muted-foreground">{{ $t('ssh.colContent') }}</th>
              <th class="px-2.5 py-2 text-left font-medium text-muted-foreground" style="width: 210px">{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedScripts" :key="item.id" class="h-10 border-b border-border/60 transition-colors hover:bg-accent/50">
              <td class="overflow-hidden px-2.5 font-semibold">{{ item.name }}</td>
              <td class="overflow-hidden px-2.5">{{ serverName(item.server_id) }}</td>
              <td class="overflow-hidden px-2.5 font-mono">{{ item.cron || '-' }}</td>
              <td class="overflow-hidden px-2.5">
                <ops-switch
                  v-if="item.cron"
                  size="small"
                  :value="item.sched_enabled"
                  @update:value="(v: boolean) => toggleSched(item, v)"
                />
                <span v-else class="text-muted-foreground">-</span>
              </td>
              <td class="content-cell overflow-hidden px-2.5 font-mono" :title="item.content">{{ item.content }}</td>
              <td class="overflow-hidden px-2.5">
                <div class="flex gap-1">
                  <Button variant="outline" size="sm" class="act text-primary" @click="askRun(item)">{{ $t('ssh.run') }}</Button>
                  <Button variant="outline" size="sm" class="act" @click="openEdit(item)">{{ $t('common.edit') }}</Button>
                  <Button variant="outline" size="sm" class="act text-destructive hover:text-destructive" @click="removeTarget = item">{{ $t('common.delete') }}</Button>
                </div>
              </td>
            </tr>
            <tr v-if="!scripts.length && !loading">
              <td colspan="7"><EmptyState :title="$t('ssh.empty')" /></td>
            </tr>
          </tbody>
          </table>
        </div>
      </CardContent>
    </Card>

    <!-- 编辑/新增脚本 -->
    <Dialog :open="editShow" @update:open="(v: boolean) => (editShow = v)">
      <DialogContent class="w-[640px] max-w-[94vw]" @escape-key-down="blockDismiss" @interact-outside="blockDismiss">
        <DialogHeader>
          <DialogTitle>{{ editingId ? $t('ssh.editTitle') : $t('ssh.createTitle') }}</DialogTitle>
        </DialogHeader>
        <div class="flex flex-col gap-3">
          <div class="flex flex-col gap-1.5">
            <span class="text-sm">{{ $t('ssh.formName') }} <span class="text-destructive">*</span></span>
            <Input v-model="form.name" :placeholder="$t('ssh.namePh')" />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-sm">{{ $t('ssh.isCron') }}</span>
            <ops-switch v-model:value="isCron" />
          </div>
          <div v-if="isCron" class="flex flex-col gap-1.5">
            <span class="text-sm">{{ $t('ssh.cronLabel') }}</span>
            <div class="cron-block">
              <div class="flex items-center gap-2">
                <Input
                  v-model="form.cron"
                  :placeholder="$t('ssh.cronPh')"
                  class="flex-1 font-mono"
                  @blur="testCron"
                />
                <Button variant="outline" size="sm" :disabled="cronTesting" @click="testCron">
                  <LoaderCircle v-if="cronTesting" class="animate-spin" />
                  {{ $t('ssh.cronTest') }}
                </Button>
              </div>
              <!-- 有结果才渲染（不测试不留空白）；打开弹窗时已重置 -->
              <div v-if="cronInvalid || cronNextRuns.length" class="cron-feedback" :class="{ invalid: cronInvalid }">
                <template v-if="cronInvalid">{{ $t('ssh.cronInvalid') }}</template>
                <template v-else-if="cronNextRuns.length">
                  {{ $t('ssh.cronNext') }}<template v-if="cronTzLabel">（{{ cronTzLabel }}）</template>
                  <div v-for="(run, i) in cronNextRuns" :key="i" class="font-mono">{{ run }}</div>
                </template>
              </div>
            </div>
          </div>
          <div class="flex flex-col gap-1.5">
            <span class="text-sm">{{ $t('ssh.bindServer') }} <span class="text-destructive">*</span></span>
            <Select :model-value="form.server_id ?? ''" @update:model-value="(v: unknown) => (form.server_id = (v as string) || null)">
              <SelectTrigger :placeholder="$t('ssh.serverPh')" />
              <SelectContent>
                <SelectItem v-for="s in servers" :key="s.value" :value="s.value">{{ s.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex items-start gap-2">
            <span class="shrink-0 pt-2 text-sm">{{ $t('ssh.formContent') }} <span class="text-destructive">*</span></span>
            <Textarea v-model="form.content" :rows="10" :spellcheck="false" :placeholder="$t('ssh.contentPh')" class="flex-1 font-mono" />
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <Button variant="outline" :disabled="testing" @click="testScript">
            <LoaderCircle v-if="testing" class="animate-spin" />
            {{ $t('ssh.test') }}
          </Button>
          <Button variant="outline" @click="editShow = false">{{ $t('common.cancel') }}</Button>
          <Button @click="save">{{ $t('common.save') }}</Button>
        </div>
      </DialogContent>
    </Dialog>

    <!-- 执行确认 + 黑色 console（可全屏；标题行右侧全屏切换，Dialog 自带关闭 X） -->
    <Dialog :open="runShow" @update:open="(v: boolean) => (runShow = v)">
      <DialogContent
        :class="runFullscreen
          ? 'flex h-[92vh] max-h-[92vh] w-[96vw] max-w-[96vw] flex-col'
          : 'w-[920px] max-w-[94vw]'"
        @escape-key-down="blockDismiss" @interact-outside="blockDismiss"
      >
        <div class="flex items-center justify-between gap-2 pr-7">
          <DialogTitle class="text-base font-semibold">
            {{ $t('ssh.runTitle', { name: runTarget?.name ?? '' }) }}
          </DialogTitle>
          <button
            type="button"
            class="flex size-7 cursor-pointer items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            :title="runFullscreen ? $t('ssh.restore') : $t('ssh.fullscreen')"
            @click="runFullscreen = !runFullscreen"
          >
            <Shrink v-if="runFullscreen" class="size-4" />
            <Expand v-else class="size-4" />
          </button>
        </div>
        <p class="run-desc">
          {{ $t('ssh.runDesc', { server: runTarget ? serverName(runTarget.server_id) : '' }) }}
        </p>
        <div v-if="running" class="console-live">{{ $t('ssh.executing') }}</div>
        <div ref="consoleEl" class="console" :class="{ 'console-max': runFullscreen }">
          <template v-if="runOutput">{{ runOutput }}</template>
          <div v-else-if="running" class="console-running">{{ $t('ssh.noOutput') }}</div>
          <span v-else class="text-muted-foreground">{{ $t('ssh.clickToRun') }}</span>
        </div>
        <div v-if="runTimedOut" class="timeout-note">
          {{ $t('ssh.timeoutNote') }}
        </div>
        <div class="flex items-center justify-between gap-2" :class="runFullscreen ? 'mt-auto pt-2' : ''">
          <Button variant="outline" :disabled="running" @click="backToEdit">{{ $t('ssh.backToEdit') }}</Button>
          <div class="flex gap-2">
            <Button variant="outline" @click="runShow = false">{{ $t('common.close') }}</Button>
            <ClickSpark>
              <Button variant="destructive" :disabled="running" @click="assessAndRun">
                <LoaderCircle v-if="running" class="animate-spin" />
                {{ $t('ssh.confirmRun') }}
              </Button>
            </ClickSpark>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <!-- 删除确认 -->
    <AlertDialog :open="!!removeTarget" @update:open="(v: boolean) => { if (!v) removeTarget = null }">
      <AlertDialogContent @escape-key-down="blockDismiss" @interact-outside="blockDismiss">
        <AlertDialogBody>
          <p class="text-sm">{{ $t('ssh.deleteConfirm', { name: removeTarget?.name ?? '' }) }}</p>
        </AlertDialogBody>
        <div class="flex justify-end gap-2 pt-2">
          <AlertDialogCancel>{{ $t('common.cancel') }}</AlertDialogCancel>
          <AlertDialogAction @click="removeTarget ? remove(removeTarget) : undefined">{{ $t('common.delete') }}</AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>

    <!-- 高风险命令二次确认（WARN 级；BLOCK 级直接拒绝不会到这里） -->
    <AlertDialog :open="riskConfirm !== null" @update:open="(v: boolean) => { if (!v) riskConfirm = null }">
      <AlertDialogContent>
        <AlertDialogBody>
          <h2 class="text-base font-semibold">{{ $t('ssh.riskTitle') }}</h2>
          <p class="text-sm text-muted-foreground">{{ $t('ssh.riskDesc') }}</p>
          <ul class="mt-1 list-disc pl-5 text-sm text-destructive">
            <li v-for="pt in riskConfirm?.patterns ?? []" :key="pt">{{ pt }}</li>
          </ul>
        </AlertDialogBody>
        <div class="flex justify-end gap-2 pt-3">
          <AlertDialogCancel>{{ $t('common.cancel') }}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="riskConfirmRun">
            {{ $t('ssh.riskConfirm') }}
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>

<style scoped>
.content-cell {
  /* 多行脚本紧凑渲染（换行保留、行距正常）——原 -webkit-box+line-clamp hack 会把行距拉出大空隙 */
  white-space: pre-line;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}
.console {
  background: #0d1117;
  color: #d1d5db;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.35;
  min-height: 220px;
  max-height: 480px;
  overflow: auto;
  white-space: pre;
  overflow-x: auto;
  font-family: ui-monospace, Consolas, monospace;
}
.console-max {
  max-height: none;
  flex: 1;
  min-height: 300px;
}
.cron-feedback {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ops-healthy);
  line-height: 1.5;
}
.cron-feedback.invalid {
  color: var(--ops-critical);
}
.console-live {
  color: var(--ops-warning);
  font-size: 12px;
  margin-bottom: 4px;
}
.run-desc {
  margin-bottom: 8px;
  color: var(--ops-text-2);
  font-size: 13px;
}
.timeout-note {
  color: var(--ops-critical);
  font-size: 12px;
  margin-top: 8px;
}
.console-running {
  color: var(--ops-warning);
  white-space: pre-wrap;
}
.act {
  min-width: 44px;
}
</style>
