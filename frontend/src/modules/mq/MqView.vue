<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NButton, NCard, NSelect, NSpace, NTable, NTag, useMessage } from 'naive-ui'
import StatusBadge from '../../components/StatusBadge.vue'
import { useSiteStore } from '../../stores/site'
import { mqApi, type AddressRow, type MqOverview, type QueueRow } from './api'

const siteStore = useSiteStore()
const message = useMessage()

const instances = ref<Array<{ label: string; value: string }>>([])
const instanceId = ref<string | null>(null)
const overview = ref<MqOverview | null>(null)
const queues = ref<QueueRow[]>([])
const addresses = ref<AddressRow[]>([])

async function loadInstances() {
  const siteId = siteStore.currentSiteId
  if (!siteId) return
  try {
    const { sitesApi } = await import('../sites/api')
    const list = await sitesApi.listResources(siteId, 'mq')
    instances.value = list.map((r) => ({ label: r.name, value: r.id }))
    if (!instanceId.value || !list.some((r) => r.id === instanceId.value)) {
      instanceId.value = list[0]?.id ?? null
    }
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function load() {
  const siteId = siteStore.currentSiteId
  if (!siteId || !instanceId.value) return
  try {
    const [o, q, a] = await Promise.all([
      mqApi.overview(siteId, instanceId.value),
      mqApi.queues(siteId, instanceId.value).catch(() => [] as QueueRow[]),
      mqApi.addresses(siteId, instanceId.value).catch(() => [] as AddressRow[]),
    ])
    overview.value = o
    queues.value = q
    addresses.value = a
  } catch (e) {
    overview.value = null
    queues.value = []
    addresses.value = []
    message.error((e as Error).message)
  }
}

onMounted(loadInstances)
watch(() => siteStore.currentSiteId, () => {
  instanceId.value = null
  overview.value = null
  loadInstances()
})
watch(instanceId, load)

function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)}${units[i]}`
}

const worstQueueStatus = computed(() => {
  const order: Record<string, number> = { CRITICAL: 3, WARNING: 2 }
  const worst = queues.value.reduce<string>(
    (acc, q) => (order[q.diagnosis?.status] ?? 0) > (order[acc] ?? 0) ? q.diagnosis.status : acc, '',
  )
  return worst || 'HEALTHY'
})
</script>

<template>
  <n-space vertical :size="12">
    <n-card size="small">
      <n-space align="center" :size="12" :wrap="false">
        <span>Broker</span>
        <n-select v-model:value="instanceId" size="small" style="width: 220px"
          placeholder="选择 Artemis" :options="instances" />
        <n-button size="small" @click="load">刷新</n-button>
        <status-badge v-if="overview" :status="overview.status" />
        <status-badge v-if="queues.length" :status="worstQueueStatus" />
      </n-space>
    </n-card>

    <template v-if="overview">
      <n-space :size="12">
        <n-card size="small" style="flex: 1" title="Broker">
          <div class="kv">
            <span>版本 <b>{{ overview.version ?? '?' }}</b></span>
            <span>运行 <b>{{ overview.uptime ?? '?' }}</b></span>
            <span>连接 <b>{{ overview.connections ?? '?' }}</b></span>
            <span>会话 <b>{{ overview.sessions ?? '?' }}</b></span>
            <span>消费者 <b>{{ overview.consumers ?? '?' }}</b></span>
            <span>地址 <b>{{ overview.addresses ?? '?' }}</b></span>
          </div>
        </n-card>
        <n-card size="small" style="flex: 1" title="JVM">
          <div class="kv">
            <span>Heap <b>{{ fmtBytes(overview.jvm.heap_used) }}</b> / {{ fmtBytes(overview.jvm.heap_max) }}</span>
            <span>NonHeap <b>{{ fmtBytes(overview.jvm.non_heap_used) }}</b></span>
            <span>线程 <b>{{ overview.jvm.threads ?? '?' }}</b></span>
            <span v-for="g in overview.jvm.gc" :key="g.name">{{ g.name }} <b>{{ g.count }}</b> 次 / {{ g.time_ms }}ms</span>
          </div>
        </n-card>
      </n-space>

      <n-card size="small" title="Queues">
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th>Queue</th><th>状态</th><th>消息数</th><th>消费者</th>
              <th>Delivering</th><th>5 分钟前</th><th>增长</th><th>问题</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in queues" :key="q.name">
              <td style="font-family: ui-monospace, monospace; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ q.name }}</td>
              <td><status-badge :status="q.diagnosis?.status" /></td>
              <td :style="{ fontWeight: (q.message_count ?? 0) > 5000 ? 700 : 400 }">{{ q.message_count ?? '-' }}</td>
              <td>{{ q.consumer_count ?? '-' }}</td>
              <td>{{ q.delivering_count ?? '-' }}</td>
              <td>{{ q.backlog_5m_ago ?? '-' }}</td>
              <td>
                <n-tag v-if="q.growth_5m != null && q.growth_5m >= 1000" type="warning" size="small" :bordered="false">
                  +{{ q.growth_5m }}
                </n-tag>
                <span v-else>{{ q.growth_5m ?? '-' }}</span>
              </td>
              <td>{{ q.diagnosis?.issues?.map((i) => i.type).join(', ') || '-' }}</td>
            </tr>
            <tr v-if="!queues.length">
              <td colspan="8" style="text-align: center; color: #999">无队列数据</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>

      <n-card size="small" title="Addresses">
        <n-table :single-line="false" size="small">
          <thead>
            <tr><th>Address</th><th>消息数</th><th>消费者</th><th>生产者</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in addresses" :key="a.name">
              <td style="font-family: ui-monospace, monospace">{{ a.name }}</td>
              <td>{{ a.message_count ?? '-' }}</td>
              <td>{{ a.consumer_count ?? '-' }}</td>
              <td>{{ a.producer_count ?? '-' }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-card>
    </template>

    <n-card v-else size="small">
      <span style="color: #999">该站点暂无 MQ 配置，或查询失败——请在「站点管理 → 资源」中添加并测试连接</span>
    </n-card>
  </n-space>
</template>

<style scoped>
.kv {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  font-size: 13px;
  color: #666;
}
.kv b {
  color: #1f2329;
}
</style>
