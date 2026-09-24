<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
import CountdownConfirm from '../../components/CountdownConfirm.vue'
import { useSiteStore } from '../../stores/site'
import { sshApi, type SshScript } from './api'

const siteStore = useSiteStore()
const message = useMessage()

const scripts = ref<SshScript[]>([])
const loading = ref(false)

// 编辑弹窗状态
const editShow = ref(false)
const editingId = ref<string | null>(null)
const form = ref<{ name: string; server_id: string | null; content: string }>({
  name: '',
  server_id: null,
  content: '',
})

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
  form.value = { name: '', server_id: servers.value[0]?.value ?? null, content: '' }
  editShow.value = true
}

function openEdit(item: SshScript) {
  editingId.value = item.id
  form.value = { name: item.name, server_id: item.server_id, content: item.content }
  editShow.value = true
}

async function save() {
  if (!siteStore.currentSiteId) return
  if (!form.value.name.trim()) {
    message.warning('名称必填')
    return
  }
  if (!form.value.server_id) {
    message.warning('必须绑定一个 Server')
    return
  }
  try {
    if (editingId.value) {
      await sshApi.update(siteStore.currentSiteId, editingId.value, { ...form.value, server_id: form.value.server_id ?? '' })
    } else {
      await sshApi.create(siteStore.currentSiteId, { ...form.value, server_id: form.value.server_id ?? '' })
    }
    message.success('已保存')
    editShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function remove(item: SshScript) {
  if (!siteStore.currentSiteId) return
  await sshApi.remove(siteStore.currentSiteId, item.id)
  message.success('已删除')
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

async function confirmRun() {
  const item = runTarget.value
  if (!item || !siteStore.currentSiteId) return
  running.value = true
  runOutput.value = ''
  try {
    const r = await sshApi.run(siteStore.currentSiteId, item.id)
    runOutput.value = (r.stdout || '') + (r.stderr ? `\n[stderr]\n${r.stderr}` : '')
    runTimedOut.value = r.timed_out
    if (r.timed_out) message.warning('执行超时（60s 上限），输出为超时前收集的部分')
  } catch (e) {
    runOutput.value = `执行失败：${(e as Error).message}`
  } finally {
    running.value = false
  }
}
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>SSH 脚本</span>
        <n-button size="small" :loading="loading" @click="load">刷新</n-button>
        <span style="color: #999; font-size: 12px">
          脚本绑定 Server 后可在其上执行（bash -s 子进程，60s 超时，记录操作日志）
        </span>
      </n-space>
    </n-card>

    <n-card size="small" title="Scripts">
      <template #header-extra>
        <n-button size="small" type="primary" @click="openCreate">新增脚本</n-button>
      </template>
      <n-spin :show="loading">
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>名称</th><th>绑定的 Server</th><th>脚本内容</th><th style="width: 150px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in scripts" :key="item.id">
              <td style="font-weight: 600">{{ item.name }}</td>
              <td>{{ serverName(item.server_id) }}</td>
              <td class="mono content-cell" :title="item.content">{{ item.content }}</td>
              <td>
                <n-space :size="4">
                  <n-button size="tiny" type="primary" ghost @click="askRun(item)">执行</n-button>
                  <n-button size="tiny" @click="openEdit(item)">编辑</n-button>
                  <countdown-confirm label="删除" :target="item.name" :seconds="5" @confirm="remove(item)" />
                </n-space>
              </td>
            </tr>
            <tr v-if="!scripts.length && !loading">
              <td colspan="4" style="text-align: center; color: #999">
                暂无脚本，点击右上角「新增脚本」（执行目标从本站点的 Server 中选择）
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
    </n-card>

    <!-- 编辑/新增脚本 -->
    <n-modal v-model:show="editShow" preset="card"
      :title="editingId ? '编辑脚本' : '新增脚本'" style="width: 640px">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="如：disk-check" />
        </n-form-item>
        <n-form-item label="绑定 Server" required>
          <n-select
            v-model:value="form.server_id"
            filterable
            :options="servers"
            placeholder="选择执行目标 Server"
          />
        </n-form-item>
        <n-form-item label="脚本内容" required>
          <n-input
            v-model:value="form.content"
            type="textarea"
            :rows="10"
            :input-props="{ spellcheck: false }"
            placeholder="bash 脚本内容（将通过 bash -s 在目标 Server 上执行）"
            class="mono"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button @click="editShow = false">取消</n-button>
          <n-button type="primary" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 执行确认 + 黑色 console -->
    <n-modal v-model:show="runShow" preset="card"
      :title="`执行脚本 · ${runTarget?.name ?? ''}`" style="width: 760px">
      <p style="margin-bottom: 10px; color: #666; font-size: 13px">
        将在 <b>{{ runTarget ? serverName(runTarget.server_id) : '' }}</b> 上执行该脚本，输出显示在下方 console。
      </p>
      <div class="console mono">
        <template v-if="runOutput">{{ runOutput }}</template>
        <span v-else-if="running" class="console-running">running...</span>
        <span v-else style="color: #6b7280">点击「确认执行」开始</span>
      </div>
      <div v-if="runTimedOut" style="color: #d03050; font-size: 12px; margin-top: 8px">
        执行超时（60s 上限），以上为超时前收集的输出
      </div>
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button @click="runShow = false">关闭</n-button>
          <n-button type="error" :loading="running" :disabled="running" @click="confirmRun">
            确认执行
          </n-button>
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
  min-height: 260px;
  max-height: 420px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.console-running {
  color: #f0a020;
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0.4; }
}
</style>
