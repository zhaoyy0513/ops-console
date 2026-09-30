<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTable,
  useMessage,
} from 'naive-ui'
import { useSiteStore } from '../../stores/site'
import { ContractOutline, ExpandOutline } from '@vicons/ionicons5'
import api from '../../api'
import OpsSwitch from '../../components/OpsSwitch.vue'
import EmptyState from '../../components/EmptyState.vue'
import { sshApi, type SshScript } from './api'

const siteStore = useSiteStore()
const message = useMessage()
const { t } = useI18n()

const scripts = ref<SshScript[]>([])
const loading = ref(false)

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
  // 展示目标：临时对象（仅用于 console 标题与描述），编辑弹窗保持打开
  runTarget.value = {
    id: '',
    name: form.value.name.trim() || t('ssh.unsaved'),
    server_id: form.value.server_id,
    content: form.value.content,
    enabled: true,
  }
  runShow.value = true
  confirmRun() // 流式：输出实时进入 console
  testing.value = false
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

/** 流式执行（测试流 id 为空时跑表单内容；表格流按 id）。
 *  每次执行 console 全新开始（互不影响）；输出实时追加并跟随滚动。 */
function confirmRun() {
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
    ? sshApi.runStream(siteStore.currentSiteId, item.id, onChunk)
    : sshApi.runAdhocStream(
        siteStore.currentSiteId, form.value.server_id ?? '', form.value.content, onChunk)
}
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>{{ $t('ssh.title') }}</span>
        <n-button size="small" :loading="loading" @click="load">{{ $t('common.refresh') }}</n-button>
        <span style="color: #999; font-size: 12px">{{ $t('ssh.hintShort') }}</span>
      </n-space>
    </n-card>

    <n-card size="small" :title="$t('ssh.scripts')">
      <template #header-extra>
        <n-button size="small" type="primary" @click="openCreate">{{ $t('ssh.newScript') }}</n-button>
      </template>
      <n-spin :show="loading">
        <!-- overflow-x:auto：窄窗口时表格内部横向滚动，不撑破页面 -->
        <div class="table-scroll">
          <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('ssh.colName') }}</th><th style="width: 22%">{{ $t('ssh.colServer') }}</th><th style="width: 100px">{{ $t('ssh.colCron') }}</th><th style="width: 70px">{{ $t('ssh.colSched') }}</th><th>{{ $t('ssh.colContent') }}</th><th style="width: 210px">{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in scripts" :key="item.id">
              <td style="font-weight: 600">{{ item.name }}</td>
              <td>{{ serverName(item.server_id) }}</td>
              <td class="mono">{{ item.cron || '-' }}</td>
              <td>
                <ops-switch
                  v-if="item.cron"
                  size="small"
                  :value="item.sched_enabled"
                  @update:value="(v: boolean) => toggleSched(item, v)"
                />
                <span v-else style="color: #999">-</span>
              </td>
              <td class="mono content-cell" :title="item.content">{{ item.content }}</td>
              <td>
                <n-space :size="4" :wrap="false">
                  <n-button class="act" size="tiny" type="primary" ghost @click="askRun(item)">{{ $t('ssh.run') }}</n-button>
                  <n-button class="act" size="tiny" @click="openEdit(item)">{{ $t('common.edit') }}</n-button>
                  <n-popconfirm @positive-click="remove(item)">
                    <template #trigger>
                      <n-button class="act" size="tiny" type="error" ghost>{{ $t('common.delete') }}</n-button>
                    </template>
                    {{ $t('ssh.deleteConfirm', { name: item.name }) }}
                  </n-popconfirm>
                </n-space>
              </td>
            </tr>
            <tr v-if="!scripts.length && !loading">
              <td :colspan="7"><EmptyState :title="$t('ssh.empty')" /></td>
            </tr>
          </tbody>
          </n-table>
        </div>
      </n-spin>
    </n-card>

    <!-- 编辑/新增脚本 -->
    <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="editShow" preset="card"
      :title="editingId ? $t('ssh.editTitle') : $t('ssh.createTitle')" style="width: 640px; max-width: 94vw">
      <n-form label-placement="top">
        <n-form-item :label="$t('ssh.formName')" required>
          <n-input v-model:value="form.name" :placeholder="$t('ssh.namePh')" />
        </n-form-item>
        <n-form-item :label="$t('ssh.isCron')">
          <ops-switch v-model:value="isCron" />
        </n-form-item>
        <n-form-item v-if="isCron" :label="$t('ssh.cronLabel')" :show-feedback="false">
          <div class="cron-block">
            <div class="cron-row">
              <n-input
                v-model:value="form.cron"
                size="small"
                :placeholder="$t('ssh.cronPh')"
                class="mono"
                style="flex: 1"
                @blur="testCron"
              />
              <n-button size="small" :loading="cronTesting" @click="testCron">{{ $t('ssh.cronTest') }}</n-button>
            </div>
            <!-- 有结果才渲染（不测试不留空白）；打开弹窗时已重置 -->
            <div v-if="cronInvalid || cronNextRuns.length" class="cron-feedback" :class="{ invalid: cronInvalid }">
              <template v-if="cronInvalid">{{ $t('ssh.cronInvalid') }}</template>
              <template v-else-if="cronNextRuns.length">
                {{ $t('ssh.cronNext') }}<template v-if="cronTzLabel">（{{ cronTzLabel }}）</template>
                <div v-for="(t, i) in cronNextRuns" :key="i" class="cron-run">{{ t }}</div>
              </template>
            </div>
          </div>
        </n-form-item>
        <n-form-item :label="$t('ssh.bindServer')" required>
          <n-select
            v-model:value="form.server_id"
            filterable
            :options="servers"
            :placeholder="$t('ssh.serverPh')"
          />
        </n-form-item>
        <n-form-item :label="$t('ssh.formContent')" required>
          <n-input
            v-model:value="form.content"
            type="textarea"
            :rows="10"
            :input-props="{ spellcheck: false }"
            :placeholder="$t('ssh.contentPh')"
            class="mono"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button :loading="testing" @click="testScript">{{ $t('ssh.test') }}</n-button>
          <n-button @click="editShow = false">{{ $t('common.cancel') }}</n-button>
          <n-button type="primary" @click="save">{{ $t('common.save') }}</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 执行确认 + 黑色 console（可全屏；header-extra 的全屏按钮位于关闭按钮左侧） -->
    <n-modal :mask-closable="false" :close-on-esc="false"
      v-model:show="runShow"
      preset="card"
      :title="$t('ssh.runTitle', { name: runTarget?.name ?? '' })"
      :style="runFullscreen
        ? { width: '96vw', maxWidth: '96vw', height: '92vh', display: 'flex', flexDirection: 'column' }
        : { width: '920px', maxWidth: '94vw' }"
    >
      <template #header-extra>
        <span
          class="fullscreen-btn"
          :title="runFullscreen ? $t('ssh.restore') : $t('ssh.fullscreen')"
          @click="runFullscreen = !runFullscreen"
        >
          <n-icon size="18" :component="runFullscreen ? ContractOutline : ExpandOutline" />
        </span>
      </template>
      <p class="run-desc">
        {{ $t('ssh.runDesc', { server: runTarget ? serverName(runTarget.server_id) : '' }) }}
      </p>
      <div v-if="running" class="console-live">{{ $t('ssh.executing') }}</div>
      <div ref="consoleEl" class="console mono" :class="{ 'console-max': runFullscreen }">
        <template v-if="runOutput">{{ runOutput }}</template>
        <div v-else-if="running" class="console-running">{{ $t('ssh.noOutput') }}</div>
        <span v-else style="color: #6b7280">{{ $t('ssh.clickToRun') }}</span>
      </div>
      <div v-if="runTimedOut" class="timeout-note">
        {{ $t('ssh.timeoutNote') }}
      </div>
      <template #footer>
        <n-space justify="space-between" :size="8">
          <n-button :disabled="running" @click="backToEdit">{{ $t('ssh.backToEdit') }}</n-button>
          <n-space :size="8">
            <n-button @click="runShow = false">{{ $t('common.close') }}</n-button>
            <n-button type="error" :loading="running" :disabled="running" @click="confirmRun">
              {{ $t('ssh.confirmRun') }}
            </n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>
  </n-space>
</template>

<style scoped>
/* 窄窗口：表格在容器内横向滚动（列固定宽 22%/100/70/210px 之和可能超出容器） */
.table-scroll {
  overflow-x: auto;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.content-cell {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.4;
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
}
.console-max {
  max-height: none;
  height: calc(92vh - 230px);
  min-height: 300px;
}
.cron-block {
  width: 100%;
}
.cron-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cron-feedback {
  margin-top: 6px;
  font-size: 12px;
  color: #18a058;
  line-height: 1.5;
}
.cron-feedback.invalid {
  color: #d03050;
}
.cron-run {
  font-family: ui-monospace, monospace;
}
.fullscreen-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 2px;
  border-radius: 3px;
  color: #666;
  cursor: pointer;
}
.fullscreen-btn:hover {
  color: #1f2329;
  background: #f2f3f5;
}
.console-live {
  color: #f0a020;
  font-size: 12px;
  margin-bottom: 4px;
}
.run-desc {
  margin-bottom: 8px;
  color: #666;
  font-size: 13px;
}
.timeout-note {
  color: #d03050;
  font-size: 12px;
  margin-top: 8px;
}
.console-running {
  color: #f0a020;
  white-space: pre-wrap;
}
</style>
<style scoped>
/* 操作列三按钮统一规格 */
.act {
  min-width: 44px;
}
/* 固定表格布局：内容列再长也不挤歪其他列（:deep 穿透 n-table 内部 <table>，
   裸 table 选择器在 scoped 下匹配不到子组件内部元素——之前的修复因此未生效） */
:deep(table) {
  width: 100%;
  table-layout: fixed;
}
:deep(td) {
  overflow: hidden;
}
</style>

<style>
/* 全屏时卡片内容纵向撑满（modal teleport 到 body，scoped 够不着） */
.n-modal.n-card[style*="92vh"] {
  display: flex;
  flex-direction: column;
}
.n-modal.n-card[style*="92vh"] .n-card__content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.n-modal.n-card[style*="92vh"] .console-max {
  flex: 1;
}
</style>
