<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NDrawer, NDrawerContent, NInput, NSelect, NSpace, NSpin, NTable, useMessage } from 'naive-ui'
import { ROBOT_FIELDS } from '../robot/fields'

const props = defineProps<{
  show: boolean
  siteId: string
  robot: {
    id: string
    name: string
    field_map?: Record<string, string> | null
    value_map?: Record<string, Record<string, string>> | null
  } | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

// 业务字段列表由 robot/fields.ts 公用定义驱动（与 Robot 页表头同源）
const BIZ_FIELDS = ROBOT_FIELDS

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const jsonFields = ref<string[]>([])
const sample = ref<Record<string, unknown> | null>(null)
// 两列独立配置：绑定字段（下拉）与模板（输入框）；保存时模板优先
const bindings = ref<Record<string, string | null>>({})
const templates = ref<Record<string, string>>({})
// 值->展示映射（枚举翻译），紧凑格式 "1=CREATE, 2=Free"；每实例独立
const valueMaps = ref<Record<string, string>>({})

/** 解析 "1=CREATE, 2=Free"（支持中英文逗号）；非法片段忽略 */
function parseValueMap(s: string | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  for (const part of (s ?? '').split(/[,，]/)) {
    const i = part.indexOf('=')
    if (i > 0) {
      const k = part.slice(0, i).trim()
      const v = part.slice(i + 1).trim()
      if (k) out[k] = v
    }
  }
  return out
}

function serializeValueMap(m: Record<string, string> | undefined): string {
  return Object.entries(m ?? {}).map(([k, v]) => `${k}=${v}`).join(', ')
}

/** 最终展示：取值/模板求值 -> 值映射查表（字符串化匹配，未命中原样） */
function applyValueMap(v: unknown, key: string): string {
  const m = parseValueMap(valueMaps.value[key])
  return m ? (m[String(v)] ?? String(v ?? '-')) : String(v ?? '-')
}

function isTemplate(v: string | null | undefined): boolean {
  return !!v && v.includes('{')
}

/** 预览求值：模板优先（{xxx} 用示例数据插值），否则取绑定字段值；再过值映射 */
function preview(key: string): string {
  if (!sample.value) return '-'
  let v: unknown
  const tpl = templates.value[key]?.trim()
  if (tpl) {
    v = tpl.replace(/\{(\w+)\}/g, (_, f) => String(sample.value?.[f] ?? ''))
  } else {
    const b = bindings.value[key]
    v = b ? sample.value[b] : sample.value[key]
  }
  return applyValueMap(v, key)
}

async function fetchSample() {
  if (!props.show || !props.siteId || !props.robot?.id) return
  loading.value = true
  try {
    const { robotApi } = await import('../robot/api')
    const result = await robotApi.sampleFields(props.siteId, props.robot.id)
    jsonFields.value = result.fields
    sample.value = result.sample
    // 已有映射回填：含 { 的值归模板列，否则归绑定列
    const b: Record<string, string | null> = {}
    const t: Record<string, string> = {}
    for (const [k, v] of Object.entries(props.robot.field_map ?? {})) {
      if (isTemplate(v)) t[k] = v
      else b[k] = v
    }
    bindings.value = b
    templates.value = t
    // 值映射回填（序列化为紧凑文本）
    const vm: Record<string, string> = {}
    for (const [k, m] of Object.entries(props.robot.value_map ?? {})) {
      vm[k] = serializeValueMap(m)
    }
    valueMaps.value = vm
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
  // 模板优先；无模板用绑定；两者皆空不存
  const clean: Record<string, string> = {}
  for (const f of BIZ_FIELDS) {
    const tpl = templates.value[f.key]?.trim()
    const bind = bindings.value[f.key]?.trim()
    if (tpl) clean[f.key] = tpl
    else if (bind) clean[f.key] = bind
  }
  // 值映射：有内容才存
  const vClean: Record<string, Record<string, string>> = {}
  for (const f of BIZ_FIELDS) {
    const m = parseValueMap(valueMaps.value[f.key])
    if (Object.keys(m).length) vClean[f.key] = m
  }
  const { sitesApi } = await import('./api')
  try {
    await sitesApi.updateResource(props.siteId, 'robots', props.robot.id, {
      field_map: Object.keys(clean).length ? clean : null,
      value_map: Object.keys(vClean).length ? vClean : null,
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
  <n-drawer :show="props.show" :width="760" placement="right"
    @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`字段映射 · ${props.robot?.name ?? ''}`" closable>
      <n-spin :show="loading">
        <p style="margin-bottom: 12px; color: #666; font-size: 13px">
          绑定字段 = 直接取该 JSON 字段的值；模板 = 按模板拼接，用 <code>{x}</code> 引用 JSON 字段（如 <code>({x},{y})</code> 合成坐标）；
          值映射 = 把取到的值翻译成展示文本（如 <code>1=CREATE, 2=Free</code>），未命中显示原值。
          <b>绑定与模板都填时模板优先</b>；都留空走内置自动识别。
        </p>
        <n-table :single-line="false" size="small">
          <thead>
            <tr>
              <th style="width: 16%">业务字段（平台展示）</th>
              <th style="width: 22%">绑定 JSON 字段</th>
              <th style="width: 22%">模板（优先）</th>
              <th style="width: 22%">值映射（枚举翻译）</th>
              <th>当前值预览</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in BIZ_FIELDS" :key="f.key">
              <td style="font-weight: 600">{{ f.label }}</td>
              <td>
                <n-select
                  v-model:value="bindings[f.key]"
                  size="small"
                  clearable
                  filterable
                  :options="jsonFields.map((jf) => ({ label: jf, value: jf }))"
                  placeholder="自动识别"
                  style="width: 100%"
                />
              </td>
              <td>
                <n-input
                  v-model:value="templates[f.key]"
                  size="small"
                  placeholder="如 ({x},{y})"
                />
              </td>
              <td>
                <n-input
                  v-model:value="valueMaps[f.key]"
                  size="small"
                  placeholder="如 1=CREATE, 2=Free"
                />
              </td>
              <td style="font-family: ui-monospace, monospace; font-size: 12px; word-break: break-all">
                {{ preview(f.key) }}
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
