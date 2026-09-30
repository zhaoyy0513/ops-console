<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NInput, NModal, NRadio, NSelect, NSpace, NSpin, NTable, useMessage } from 'naive-ui'
import { DEVICE_FIELDS } from '../device/fields'

const props = defineProps<{
  show: boolean
  siteId: string
  device: {
    id: string
    name: string
    field_map?: Record<string, string> | null
    value_map?: Record<string, Record<string, string>> | null
  } | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

// 业务字段列表由 device/fields.ts 公用定义驱动（与 Device 页表头同源）
const BIZ_FIELDS = DEVICE_FIELDS

const message = useMessage()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const jsonFields = ref<string[]>([])
const sample = ref<Record<string, unknown> | null>(null)
// 两列独立配置：绑定字段（下拉）与模板（输入框）；保存时模板优先
const bindings = ref<Record<string, string | null>>({})
const templates = ref<Record<string, string>>({})
// 值->展示映射（枚举翻译），紧凑格式 "1=CREATE, 2=Free"；每实例独立
const valueMaps = ref<Record<string, string>>({})
// 当前编辑实例标识：控件 key 绑定它，切换 Device 时销毁重建（修复 textarea 高度残留）
const deviceKey = ref('')

/** 解析值映射：换行或逗号分隔的 k=v（支持中英文逗号）；非法片段忽略 */
function parseValueMap(s: string | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  for (const part of (s ?? '').split(/\r?\n|,|，/)) {
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
  return Object.entries(m ?? {}).map(([k, v]) => `${k}=${v}`).join('\n')
}

/** 最终展示：取值/模板求值 -> 值映射查表（字符串化匹配，未命中原样） */
function applyValueMap(v: unknown, key: string): string {
  const m = parseValueMap(valueMaps.value[key])
  return m ? (m[String(v)] ?? String(v ?? '-')) : String(v ?? '-')
}

function isTemplate(v: string | null | undefined): boolean {
  return !!v && v.includes('{')
}

/** 预览：仅反映显式配置（绑定/模板 -> 值映射）；未配置显示提示，
 *  不再回退 sample[key] —— 那与后端真实取值（候选+大小写匹配）不一致，造成误导 */
function preview(key: string): string {
  if (!sample.value) return '-'
  const tpl = templates.value[key]?.trim()
  const b = bindings.value[key]
  if (!tpl && !b) return t('fieldmap.unconfigured')
  let v: unknown
  if (tpl) {
    v = tpl.replace(/\{(\w+)\}/g, (_, f) => String(sample.value?.[f] ?? ''))
  } else {
    v = sample.value[b as string] ?? '-'
  }
  return applyValueMap(v, key)
}

async function fetchSample() {
  if (!props.show || !props.siteId || !props.device?.id) return
  loading.value = true
  deviceKey.value = `${props.device.id}#${Date.now()}`  // 每次打开换新 key，控件全新（无高度残留）
  try {
    const { deviceApi } = await import('../device/api')
    const result = await deviceApi.sampleFields(props.siteId, props.device.id)
    jsonFields.value = result.fields
    sample.value = result.sample
    // 已有映射回填（模板归模板列，其余归绑定列）
    applyMapping(props.device.field_map, props.device.value_map)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

watch(() => [props.show, props.device?.id] as const, ([show]) => {
  if (show) fetchSample()
})

// ---------- 克隆：从全局任意站点/实例复制映射配置（仅回显，保存才生效） ----------
const cloneShow = ref(false)
const cloneList = ref<Array<{
  site_id: string; site_name: string; device_id: string; device_name: string
  field_map: Record<string, string> | null; value_map: Record<string, Record<string, string>> | null
}>>([])
const cloneLoading = ref(false)
const cloneSelected = ref<string | null>(null)

async function openClone() {
  cloneShow.value = true
  cloneSelected.value = null
  cloneLoading.value = true
  try {
    const { deviceApi } = await import('../device/api')
    const all = await deviceApi.listMappings()
    // 排除当前编辑的实例（自己克隆自己没有意义）
    cloneList.value = all.filter(
      (x) => !(x.site_id === props.siteId && x.device_id === props.device?.id),
    )
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    cloneLoading.value = false
  }
}

function applyClone() {
  const src = cloneList.value.find((x) => `${x.site_id}/${x.device_id}` === cloneSelected.value)
  if (!src) {
    message.warning(t('fieldmap.pickSource'))
    return
  }
  applyMapping(src.field_map, src.value_map)
  deviceKey.value = `${deviceKey.value}#clone`  // 强制重建控件，确保覆盖/清空立即生效
  cloneShow.value = false
  message.success(t('fieldmap.cloned', { site: src.site_name, device: src.device_name }))
}

/** 映射配置 -> 表单回显（fetchSample 与克隆共用） */
function applyMapping(
  fieldMap?: Record<string, string> | null,
  valueMap?: Record<string, Record<string, string>> | null,
) {
  const b: Record<string, string | null> = {}
  const t: Record<string, string> = {}
  for (const [k, v] of Object.entries(fieldMap ?? {})) {
    if (isTemplate(v)) t[k] = v
    else b[k] = v
  }
  bindings.value = b
  templates.value = t
  const vm: Record<string, string> = {}
  for (const [k, m] of Object.entries(valueMap ?? {})) {
    vm[k] = serializeValueMap(m)
  }
  valueMaps.value = vm
}

async function save() {
  if (!props.siteId || !props.device?.id) return
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
    await sitesApi.updateResource(props.siteId, 'devices', props.device.id, {
      field_map: Object.keys(clean).length ? clean : null,
      value_map: Object.keys(vClean).length ? vClean : null,
    })
    message.success(t('fieldmap.mappingSaved'))
    emit('update:show', false)
    emit('saved')
  } catch (e) {
    message.error((e as Error).message)
  }
}
</script>

<template>
  <n-drawer :mask-closable="false" :close-on-esc="false" :show="props.show" :width="920" placement="right"
    @update:show="emit('update:show', $event)">
    <n-drawer-content :title="$t('fieldmap.title', { name: props.device?.name ?? '' })" closable>
      <n-spin :show="loading">
        <p style="margin-bottom: 12px; color: #666; font-size: 13px">
          {{ $t('fieldmap.intro') }}
        </p>
        <div class="field-groups">
          <div v-for="f in BIZ_FIELDS" :key="f.key" class="field-group">
            <div class="field-title">{{ $t(`device.fields.${f.key}`) }}</div>
            <div class="field-controls">
              <div class="f-item">
                <div class="f-label">{{ $t('fieldmap.bindLabel') }}</div>
                <!-- key 绑定 deviceKey：切换实例时销毁重建，杜绝上一个 Device 的内容/高度残留 -->
                <n-select
                  :key="`b-${deviceKey}-${f.key}`"
                  v-model:value="bindings[f.key]"
                  size="small"
                  clearable
                  filterable
                  :options="jsonFields.map((jf) => ({ label: jf, value: jf }))"
                  :placeholder="$t('fieldmap.selectPh')"
                  style="width: 100%"
                />
              </div>
              <div class="f-item">
                <div class="f-label">{{ $t('fieldmap.tplLabel') }}</div>
                <n-input
                  :key="`t-${deviceKey}-${f.key}`"
                  v-model:value="templates[f.key]"
                  size="small"
                  :placeholder="$t('fieldmap.tplPh')"
                />
              </div>
              <div class="f-item">
                <div class="f-label">{{ $t('fieldmap.vmLabel') }}</div>
                <n-input
                  :key="`v-${deviceKey}-${f.key}`"
                  v-model:value="valueMaps[f.key]"
                  type="textarea"
                  :rows="1"
                  :placeholder="$t('fieldmap.vmPh')"
                />
              </div>
              <div class="f-item">
                <div class="f-label">{{ $t('fieldmap.previewLabel') }}</div>
                <div class="preview mono">{{ preview(f.key) }}</div>
              </div>
            </div>
          </div>
        </div>
      </n-spin>
      <template #footer>
        <div style="display: flex; align-items: center; gap: 10px; width: 100%">
          <n-button style="background: #f08c00; color: #fff" @click="openClone">{{ $t('fieldmap.clone') }}</n-button>
          <div style="flex: 1" />
          <n-button @click="emit('update:show', false)">{{ $t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="saving" @click="save">{{ $t('fieldmap.saveMapping') }}</n-button>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>

  <!-- 克隆来源选择：列出全部站点的 Device 映射配置 -->
  <n-modal :mask-closable="false" :close-on-esc="false" v-model:show="cloneShow" preset="card" :title="$t('fieldmap.cloneTitle')" style="width: 520px">
    <p style="margin-bottom: 10px; color: #666; font-size: 13px">
      {{ $t('fieldmap.cloneIntro') }}
    </p>
    <n-spin :show="cloneLoading">
      <n-table :single-line="false" size="small" class="clone-table">
        <thead>
          <tr><th style="width: 50px">{{ $t('fieldmap.pickCol') }}</th><th style="width: 40%">{{ $t('fieldmap.siteCol') }}</th><th>{{ $t('fieldmap.deviceCol') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="x in cloneList" :key="x.site_id + '/' + x.device_id"
            class="clone-row"
            :class="{ 'clone-selected': cloneSelected === x.site_id + '/' + x.device_id }"
            @click="cloneSelected = x.site_id + '/' + x.device_id">
            <td><n-radio :checked="cloneSelected === x.site_id + '/' + x.device_id" /></td>
            <td>{{ x.site_name }}</td>
            <td>{{ x.device_name }}</td>
          </tr>
          <tr v-if="!cloneList.length && !cloneLoading">
            <td colspan="2" style="text-align: center; color: #999">{{ $t('fieldmap.noClone') }}</td>
          </tr>
        </tbody>
      </n-table>
    </n-spin>
    <template #footer>
      <n-space justify="end" :size="8">
        <n-button size="small" @click="cloneShow = false">{{ $t('common.cancel') }}</n-button>
        <n-button size="small" type="primary" :disabled="!cloneSelected" @click="applyClone">{{ $t('fieldmap.confirmClone') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
<style scoped>
.field-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field-group {
  padding-bottom: 10px;
  border-bottom: 1px solid #f5f6f8;
}
.field-group:last-child {
  border-bottom: none;
}
.field-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.field-controls {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.f-item {
  flex: 1;
  min-width: 0;
}
.f-label {
  color: #86909c;
  font-size: 12px;
  margin-bottom: 4px;
}
.preview {
  font-size: 12px;
  word-break: break-all;
  padding: 5px 0;
  min-height: 24px;
}
</style>
