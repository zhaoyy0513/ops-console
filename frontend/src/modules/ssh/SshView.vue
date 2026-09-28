<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCard,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTable,
  useMessage,
} from 'naive-ui'
import { useSiteStore } from '../../stores/site'
import api from '../../api'
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
    if (!v) form.value.cron = ''
  },
})

const cronTesting = ref(false)
const cronNextRuns = ref<string[]>([])
const cronInvalid = ref(false)

async function testCron() {
  cronNextRuns.value = []
  if (!form.value.cron.trim()) return
  cronTesting.value = true
  try {
    const r = await api.post('/ssh/validate-cron', { cron: form.value.cron })
    cronNextRuns.value = (r as any).next_runs
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

/** 编辑弹窗内的测试：先保存（新增会落库），再打开共用 console 执行 */
const testing = ref(false)
async function testScript() {
  if (!siteStore.currentSiteId) return
  testing.value = true
  try {
    if (!form.value.name.trim()) {
      // 未填名称时自动生成（避免落库无名脚本）
      form.value.name = `script-${new Date().toLocaleString('sv-SE').replace(/[-: ]/g, '')}`
    }
    let id = editingId.value
    if (!id) {
      const created = await sshApi.create(siteStore.currentSiteId, {
        ...form.value, server_id: form.value.server_id ?? '',
      })
      id = created.id
      editingId.value = id
      message.success(t('ssh.saved'))
      await load()
    } else {
      await sshApi.update(siteStore.currentSiteId, id, {
        ...form.value, server_id: form.value.server_id ?? '',
      })
      await load()
    }
    // 用表单当前内容覆盖执行目标（与保存一致），打开共用 console 并执行
    const script: SshScript = {
      id,
      name: form.value.name,
      server_id: form.value.server_id ?? '',
      content: form.value.content,
      enabled: true,
    }
    editShow.value = false
    runTarget.value = script
    runShow.value = true
    await confirmRun()
  } catch (e) {
    message.error((e as Error).message)
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

function openCreate() {
  editingId.value = null
  form.value = { name: '', server_id: servers.value[0]?.value ?? null, content: '', cron: '', sched_enabled: false }
  editShow.value = true
}

function openEdit(item: SshScript) {
  editingId.value = item.id
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

// ---------- 执行（确认 + 黑色 console） ----------
const runShow = ref(false)
const runTarget = ref<SshScript | null>(null)
const running = ref(false)
const runOutput = ref('')
const runTimedOut = ref(false)

function askRun(item: SshScript) {
  runTarget.value = item
  runOutput.value = ''
  runTimedOut.value = false
  runShow.value = true
}

function backToEdit() {
  runShow.value = false
  if (runTarget.value) {
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

async function confirmRun() {
  const item = runTarget.value
  if (!item || !siteStore.currentSiteId) return
  running.value = true
  runOutput.value = ''
  try {
    const r = await sshApi.run(siteStore.currentSiteId, item.id)
    runOutput.value = (r.stdout || '') + (r.stderr ? `\n[stderr]\n${r.stderr}` : '')
    runTimedOut.value = r.timed_out
    if (r.timed_out) message.warning(t('ssh.timeoutWarn'))
  } catch (e) {
    runOutput.value = t('ssh.runFailed', { msg: (e as Error).message })
  } finally {
    running.value = false
  }
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
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>{{ $t('ssh.colName') }}</th><th>{{ $t('ssh.colServer') }}</th><th style="width: 110px">{{ $t('ssh.colCron') }}</th><th style="width: 90px">{{ $t('ssh.colSched') }}</th><th>{{ $t('ssh.colContent') }}</th><th style="width: 150px">{{ $t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in scripts" :key="item.id">
              <td style="font-weight: 600">{{ item.name }}</td>
              <td>{{ serverName(item.server_id) }}</td>
              <td class="mono">{{ item.cron || '-' }}</td>
              <td>
                <n-switch
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
                    {{ item.name }}
                  </n-popconfirm>
                </n-space>
              </td>
            </tr>
            <tr v-if="!scripts.length && !loading">
              <td colspan="4" style="text-align: center; color: #999">
                {{ $t('ssh.empty') }}
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
    </n-card>

    <!-- 编辑/新增脚本 -->
    <n-modal v-model:show="editShow" preset="card"
      :title="editingId ? $t('ssh.editTitle') : $t('ssh.createTitle')" style="width: 640px">
      <n-form label-placement="top">
        <n-form-item :label="$t('ssh.formName')" required>
          <n-input v-model:value="form.name" :placeholder="$t('ssh.namePh')" />
        </n-form-item>
        <n-form-item :label="$t('ssh.isCron')">
          <n-switch v-model:value="isCron" />
        </n-form-item>
        <n-form-item v-if="isCron" :label="$t('ssh.cronLabel')" :feedback="cronInvalid ? $t('ssh.cronInvalid') : undefined" :validation-status="cronInvalid ? 'error' : undefined">
          <n-space vertical fill style="width: 100%">
            <n-space align="center" :size="8">
              <n-input
                v-model:value="form.cron"
                size="small"
                :placeholder="$t('ssh.cronPh')"
                class="mono"
                style="flex: 1"
                @blur="testCron"
              />
              <n-button size="small" :loading="cronTesting" @click="testCron">{{ $t('ssh.cronTest') }}</n-button>
            </n-space>
            <div v-if="cronNextRuns.length" style="font-size: 12px; color: #18a058">
              {{ $t('ssh.cronNext') }}
              <div v-for="(t, i) in cronNextRuns" :key="i" class="cron-run">{{ t }}</div>
            </div>
          </n-space>
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

    <!-- 执行确认 + 黑色 console -->
    <n-modal v-model:show="runShow" preset="card"
      :title="$t('ssh.runTitle', { name: runTarget?.name ?? '' })" style="width: 920px; max-width: 94vw">
      <p style="margin-bottom: 10px; color: #666; font-size: 13px">
        {{ $t('ssh.runDesc', { server: runTarget ? serverName(runTarget.server_id) : '' }) }}
      </p>
      <div class="console mono">
        <template v-if="runOutput">{{ runOutput }}</template>
        <span v-else-if="running" class="console-running">running...</span>
        <span v-else style="color: #6b7280">{{ $t('ssh.clickToRun') }}</span>
      </div>
      <div v-if="runTimedOut" style="color: #d03050; font-size: 12px; margin-top: 8px">
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
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.content-cell {
  display: block;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.console {
  background: #0d1117;
  color: #d1d5db;
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  min-height: 320px;
  max-height: 520px;
  overflow: auto;
  white-space: pre;
  overflow-x: auto;
}
.console-running {
  color: #f0a020;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0.4; }
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
