<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NSelect, NSpace, NSpin, NTable, useMessage } from 'naive-ui'

const props = defineProps<{
  show: boolean
  siteId: string
  robot: { id: string; name: string; field_map?: Record<string, string> | null } | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

/** 业务字段（左侧列，固定）：展示名 -> field_map 的 key */
const BIZ_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'id', label: 'Robot Code' },
  { key: 'name', label: 'Robot Name' },
  { key: 'status', label: 'Status' },
  { key: 'battery', label: 'Battery' },
  { key: 'station', label: 'Position' },
  { key: 'task', label: 'Task' },
  { key: 'error', label: 'Error' },
  { key: 'last_update', label: 'Last Update' },
]

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const jsonFields = ref<string[]>([])
const sample = ref<Record<string, unknown> | null>(null)
const mappings = ref<Record<string, string>>({})

async function fetchSample() {
  if (!props.show || !props.siteId || !props.robot?.id) return
  loading.value = true
  try {
    const { robotApi } = await import('../robot/api')
    const result = await robotApi.sampleFields(props.siteId, props.robot.id)
    jsonFields.value = result.fields
    sample.value = result.sample
    // 已有映射回填
    mappings.value = { ...(props.robot.field_map ?? {}) }
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

watch(() => [props.show, props.robot?.id] as const, ([show]) => {
  if (show) fetchSample()
})

async function save() {
  if (!props.siteId || !props.robot?.id) return
  // 清除空映射
  const clean = Object.fromEntries(
    Object.entries(mappings.value).filter(([, v]) => v),
  )
  const { sitesApi } = await import('./api')
  try {
    await sitesApi.updateResource(props.siteId, 'robots', props.robot.id, {
      field_map: Object.keys(clean).length ? clean : null,
    })
    message.success('字段映射已保存')
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error((e as Error).message)
  }
}
</script>

<template>
  <n-drawer :show="props.show" :width="640" placement="right"
    @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`字段映射 · ${props.robot?.name ?? ''}`" closable>
      <n-spin :show="loading">
        <p style="margin-bottom: 12px; color: #666; font-size: 13px">
          将左侧业务字段绑定到右侧 JSON 数据的实际字段名；支持模板拼接（如 ({x},{y})），含 {xxx} 占位符的值按模板求值；未绑定的字段走内置识别。
        </p>
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th style="width: 40%">业务字段（平台展示）</th>
              <th style="width: 35%">绑定的 JSON 字段</th>
              <th>当前值预览</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in BIZ_FIELDS" :key="f.key">
              <td style="font-weight: 600">{{ f.label }}</td>
              <td>
                <n-select
                  v-model:value="mappings[f.key]"
                  size="small"
                  clearable
                  filterable
                  :options="jsonFields.map((jf) => ({ label: jf, value: jf }))"
                  placeholder="自动识别"
                  style="width: 100%"
                />
              </td>
              <td style="font-family: ui-monospace, monospace; font-size: 12px; word-break: break-all">
                {{ mappings[f.key] && sample ? String(sample[mappings[f.key]] ?? '-') : (sample?.[f.key] ?? '-') }}
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
      <template #footer>
        <n-space justify="end" :size="8">
          <n-button @click="emit('update:show', false)">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存映射</n-button>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
