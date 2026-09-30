<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NInput, NModal, NRadio, NRadioGroup, NSelect, NSpace, NSpin, NTable, useMessage } from 'naive-ui'
import { DEVICE_FIELDS } from '../device/fields'
import type { DeviceCustomField } from '../device/api'

const props = defineProps<{
  show: boolean
  siteId: string
  device: {
    id: string
    name: string
    field_map?: Record<string, string> | null
    value_map?: Record<string, Record<string, string>> | null
    custom_fields?: DeviceCustomField[] | null
  } | null
}>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'saved'): void }>()

// 弹窗内可映射的业务字段（Device 表格保留电量列，但映射弹窗不再提供 battery 行）
const BIZ_FIELDS = DEVICE_FIELDS.filter((f) => f.key !== 'battery')
const BIZ_KEYS = new Set(BIZ_FIELDS.map((f) => f.key))
// 自定义字段上限（后端同校验）
const MAX_CUSTOM = 10

type FieldMode = 'bind' | 'template'

const message = useMessage()
const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const jsonFields = ref<string[]>([])
const sample = ref<Record<string, unknown> | null>(null)
// 每字段显式选择模式：绑定 = 直接取 JSON 字段；模板 = 自由文本 + {字段名} 占位。
// 保存时只写当前模式的取值（另一形态清空），无隐式优先级。
const modes = ref<Record<string, FieldMode>>({})
const bindings = ref<Record<string, string | null>>({})
const templates = ref<Record<string, string>>({})
// 值->展示映射（枚举翻译），紧凑格式 "1=CREATE, 2=Free"；每实例独立
const valueMaps = ref<Record<string, string>>({})
// 自定义展示字段：key 生成一次后稳定（cf_+5hex），bind/template/value_map
// 复用上面以 key 为索引的表 —— 编辑/预览逻辑与内置字段完全同构
const customFields = ref<DeviceCustomField[]>([])
// 统一行模型：内置字段（标题走 i18n，不可删改）+ 自定义字段（双语名可编辑、可删）
const rows = computed<Array<{ key: string; cf?: DeviceCustomField }>>(() => [
  ...BIZ_FIELDS.map((f) => ({ key: f.key })),
  ...customFields.value.map((cf) => ({ key: cf.key, cf })),
])
// 当前编辑实例标识：控件 key 绑定它，切换 Device 时销毁重建（修复 textarea 高度残留）
const deviceKey = ref('')

/** 新增自定义字段：稳定 key 一次性生成（保存前可删，不占用后端校验） */
function addCustom() {
  if (customFields.value.length >= MAX_CUSTOM) return
  const key = `cf_${Math.random().toString(16).slice(2, 7).padEnd(5, '0')}`
  customFields.value.push({ key, label_zh: '', label_en: '' })
}

function removeCustom(key: string) {
  customFields.value = customFields.value.filter((cf) => cf.key !== key)
}

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

/** 原始值：绑定 = sample[字段]；模板 = 花括号替换（与后端 eval_value 同规则，缺字段补空串） */
function rawValue(key: string): string {
  if (!sample.value) return '-'
  if (modes.value[key] === 'template') {
    const tpl = templates.value[key]?.trim()
    if (!tpl) return '-'
    // 与后端 eval_value 同规则：{field} 单字段；{f1,f2} 多字段逗号连接
    return tpl.replace(/\{([\w,]+)\}/g, (_, names: string) =>
      names.split(',').map((f: string) => String((sample.value as Record<string, unknown>)?.[f] ?? '')).join(','))
  }
  const b = bindings.value[key]
  if (!b) return '-'
  const v = sample.value[b]
  return v == null ? '-' : String(v)
}

/** 预览：原始值过值映射（未配置值映射原样显示）；未配置取值显示提示 */
function preview(key: string): string {
  if (!sample.value) return '-'
  const configured = modes.value[key] === 'template'
    ? !!templates.value[key]?.trim()
    : !!bindings.value[key]
  if (!configured) return t('fieldmap.unconfigured')
  const v = rawValue(key)
  const m = parseValueMap(valueMaps.value[key])
  return Object.keys(m).length ? (m[v] ?? v) : v
}

function setMode(key: string, v: string | number | boolean) {
  modes.value[key] = v as FieldMode
}

/** 模板校验：花括号内只能是字段名（逗号分隔可多个）；空括号/空格/嵌套等非法 */
function tplInvalid(tpl: string | undefined): boolean {
  if (!tpl) return false
  return /\{\s*\}|\{[^}]*[^\w,}][^}]*\}/.test(tpl) || /\{[^}]*$/.test(tpl)
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
    // 已有映射回填（含自定义字段；模板归模板，其余归绑定）
    applyMapping(props.device.field_map, props.device.value_map, props.device.custom_fields)
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
  custom_fields?: DeviceCustomField[] | null
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
  applyMapping(src.field_map, src.value_map, src.custom_fields)
  deviceKey.value = `${deviceKey.value}#clone`  // 强制重建控件，确保覆盖/清空立即生效
  cloneShow.value = false
  message.success(t('fieldmap.cloned', { site: src.site_name, device: src.device_name }))
}

/** 映射配置 -> 表单回显（fetchSample 与克隆共用）；模式按已存形态推导，绑定+模板双存按旧语义归模板 */
function applyMapping(
  fieldMap?: Record<string, string> | null,
  valueMap?: Record<string, Record<string, string>> | null,
  customs?: DeviceCustomField[] | null,
) {
  const b: Record<string, string | null> = {}
  const t: Record<string, string> = {}
  const m: Record<string, FieldMode> = {}
  for (const [k, v] of Object.entries(fieldMap ?? {})) {
    if (v.includes('{')) { t[k] = v; m[k] = 'template' }
    else { b[k] = v; m[k] = 'bind' }
  }
  for (const cf of customs ?? []) {
    if (cf.template) { t[cf.key] = cf.template; m[cf.key] = 'template' }
    else if (cf.bind) { b[cf.key] = cf.bind; m[cf.key] = 'bind' }
  }
  bindings.value = b
  templates.value = t
  modes.value = m
  const vm: Record<string, string> = {}
  for (const [k, mm] of Object.entries(valueMap ?? {})) {
    vm[k] = serializeValueMap(mm)
  }
  for (const cf of customs ?? []) {
    if (cf.value_map && Object.keys(cf.value_map).length) vm[cf.key] = serializeValueMap(cf.value_map)
  }
  valueMaps.value = vm
  // 克隆（快照副本）避免直接改到来源对象
  customFields.value = (customs ?? []).map((c) => ({ ...c }))
}

async function save() {
  if (!props.siteId || !props.device?.id) return
  // 只写当前模式的取值（另一形态不写 = 清空）；battery 等不在本弹窗内的历史映射原样保留
  const clean: Record<string, string> = {}
  for (const [k, v] of Object.entries(props.device.field_map ?? {})) {
    if (!BIZ_KEYS.has(k)) clean[k] = v
  }
  for (const f of BIZ_FIELDS) {
    const v = modes.value[f.key] === 'template'
      ? templates.value[f.key]?.trim()
      : bindings.value[f.key]?.trim()
    if (v) clean[f.key] = v
  }
  const vClean: Record<string, Record<string, string>> = {}
  for (const [k, m] of Object.entries(props.device.value_map ?? {})) {
    if (!BIZ_KEYS.has(k)) vClean[k] = m
  }
  for (const f of BIZ_FIELDS) {
    const m = parseValueMap(valueMaps.value[f.key])
    if (Object.keys(m).length) vClean[f.key] = m
  }
  // 自定义字段：同一套「单模式取值 + 值映射」规则；key 稳定，随保存写入实例配置
  const customs = customFields.value.map((cf) => {
    const tpl = (templates.value[cf.key] ?? '').trim()
    const bind = bindings.value[cf.key]?.trim() ?? null
    const m = parseValueMap(valueMaps.value[cf.key])
    const mode = modes.value[cf.key] ?? 'bind'
    return {
      key: cf.key,
      label_zh: cf.label_zh.trim(),
      label_en: cf.label_en.trim(),
      template: mode === 'template' ? (tpl || null) : null,
      bind: mode === 'bind' ? (bind || null) : null,
      value_map: Object.keys(m).length ? m : null,
    }
  })
  const { sitesApi } = await import('./api')
  try {
    await sitesApi.updateResource(props.siteId, 'devices', props.device.id, {
      field_map: Object.keys(clean).length ? clean : null,
      value_map: Object.keys(vClean).length ? vClean : null,
      custom_fields: customs.length ? customs : null,
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
  <n-drawer :mask-closable="false" :close-on-esc="false" :show="props.show" :width="1060" placement="right"
    style="max-width: 94vw"
    @update:show="emit('update:show', $event)">
    <n-drawer-content :title="$t('fieldmap.title', { name: props.device?.name ?? '' })" closable>
      <n-spin :show="loading">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
          <p style="flex: 1; margin: 0; color: #666; font-size: 13px">
            {{ $t('fieldmap.intro') }}
          </p>
          <span v-if="customFields.length >= MAX_CUSTOM" style="color: #f0a020; font-size: 12px; white-space: nowrap">
            {{ $t('device.customMax') }}
          </span>
          <n-button size="small" type="primary" ghost :disabled="customFields.length >= MAX_CUSTOM" @click="addCustom">
            + {{ $t('device.addCustom') }}
          </n-button>
        </div>
        <div class="fm-scroll">
          <div class="fm-grid">
            <div class="fm-row fm-head">
              <div class="c-name">{{ $t('fieldmap.nameLabel') }}</div>
              <div class="c-mode">{{ $t('fieldmap.modeLabel') }}</div>
              <div class="c-value">{{ $t('fieldmap.valueLabel') }}</div>
              <div class="c-raw">{{ $t('fieldmap.raw') }}</div>
              <div class="c-vm">{{ $t('fieldmap.vmLabel') }}</div>
              <div class="c-preview">{{ $t('fieldmap.preview') }}</div>
              <div class="c-del" />
            </div>
            <div v-for="row in rows" :key="row.key" class="fm-row fm-body">
              <div class="c-name" :class="{ 'c-name-biz': !row.cf }">
                <template v-if="row.cf">
                  <!-- 自定义字段：双语展示名可编辑；内置字段名固定不可改 -->
                  <n-input v-model:value="row.cf.label_zh" size="small"
                    :placeholder="$t('device.customNameZh')" />
                  <n-input v-model:value="row.cf.label_en" size="small"
                    :placeholder="$t('device.customNameEn')" />
                </template>
                <template v-else>{{ $t(`device.fields.${row.key}`) }}</template>
              </div>
              <div class="c-mode">
                <n-radio-group :value="modes[row.key] ?? 'bind'" size="small"
                  @update:value="(v) => setMode(row.key, v)">
                  <n-radio value="bind">{{ $t('fieldmap.modeBind') }}</n-radio>
                  <n-radio value="template">{{ $t('fieldmap.modeTemplate') }}</n-radio>
                </n-radio-group>
              </div>
              <div class="c-value">
                <!-- key 绑定 deviceKey：切换实例时销毁重建，杜绝上一个 Device 的内容/高度残留 -->
                <n-select
                  v-if="(modes[row.key] ?? 'bind') === 'bind'"
                  :key="`b-${deviceKey}-${row.key}`"
                  v-model:value="bindings[row.key]"
                  size="small"
                  clearable
                  filterable
                  :options="jsonFields.map((jf) => ({ label: jf, value: jf }))"
                  :placeholder="$t('fieldmap.selectPh')"
                  style="width: 100%"
                />
                <!-- 花括号示例是模板语法本身，必须硬编码（vue-i18n 会把 {x} 当占位符） -->
                <n-input
                  v-else
                  :key="`t-${deviceKey}-${row.key}`"
                  v-model:value="templates[row.key]"
                  size="small"
                  :status="tplInvalid(templates[row.key]) ? 'error' : undefined"
                  :placeholder="'({mapId},{areaId}) 或 ({mapId,areaId})'"
                />
                <div v-if="tplInvalid(templates[row.key])" class="tpl-hint">
                  {{ $t('fieldmap.tplInvalid') }}
                </div>
              </div>
              <div class="c-raw mono">{{ rawValue(row.key) }}</div>
              <div class="c-vm">
                <n-input
                  :key="`v-${deviceKey}-${row.key}`"
                  v-model:value="valueMaps[row.key]"
                  type="textarea"
                  :rows="1"
                  :placeholder="$t('fieldmap.vmPh')"
                />
              </div>
              <div class="c-preview mono">{{ preview(row.key) }}</div>
              <div class="c-del">
                <n-button v-if="row.cf" size="tiny" type="error" ghost @click="removeCustom(row.key)">
                  {{ $t('common.delete') }}
                </n-button>
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
.fm-scroll {
  overflow-x: auto;
}
.fm-grid {
  min-width: 880px;
}
.fm-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f5f6f8;
}
.fm-body:last-child {
  border-bottom: none;
}
.fm-head {
  color: #86909c;
  font-size: 12px;
  font-weight: 400;
  padding: 2px 0 6px;
  border-bottom: 1px solid #e5e6eb;
}
.c-name {
  width: 150px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.c-name-biz {
  font-weight: 600;
  font-size: 13px;
}
.c-mode {
  width: 112px;
  flex: none;
}
.c-value {
  flex: 1.2;
  min-width: 170px;
}
.tpl-hint {
  color: #d03050;
  font-size: 11px;
  line-height: 1.4;
  margin-top: 2px;
}
.c-raw {
  width: 120px;
  flex: none;
}
.c-vm {
  flex: 1;
  min-width: 150px;
}
.c-preview {
  width: 130px;
  flex: none;
}
.c-del {
  width: 52px;
  flex: none;
}
.mono {
  font-size: 12px;
  word-break: break-all;
}
</style>
