<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { message } from '@/lib/message'
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
  const tp: Record<string, string> = {}
  const m: Record<string, FieldMode> = {}
  for (const [k, v] of Object.entries(fieldMap ?? {})) {
    if (v.includes('{')) { tp[k] = v; m[k] = 'template' }
    else { b[k] = v; m[k] = 'bind' }
  }
  for (const cf of customs ?? []) {
    if (cf.template) { tp[cf.key] = cf.template; m[cf.key] = 'template' }
    else if (cf.bind) { b[cf.key] = cf.bind; m[cf.key] = 'bind' }
  }
  bindings.value = b
  templates.value = tp
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

/** 每行行模型的赋值 setter：模板编译器不允许 v-model="fn()"（左侧需可赋值），
 *  故用 :model-value + @update:model-value 直接下标赋值（对象属性可赋值）。 */
function setTpl(key: string, v: string | number) { templates.value[key] = String(v) }
function setVm(key: string, v: string | number) { valueMaps.value[key] = String(v) }
</script>

<template>
  <Dialog :open="props.show" @update:open="(v: boolean) => emit('update:show', v)">
    <DialogContent class="flex w-[1060px] max-w-[94vw] flex-col max-h-[85vh]" @escape-key-down.prevent @interact-outside.prevent>
      <DialogHeader>
        <DialogTitle>{{ $t('fieldmap.title', { name: props.device?.name ?? '' }) }}</DialogTitle>
      </DialogHeader>

      <!-- 自绘 spinner（替代 NSpin）：数据未到时挡住表格区，布局不跳 -->
      <div class="relative flex-1 overflow-y-auto">
        <div v-if="loading" class="flex h-40 items-center justify-center">
          <div class="size-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        </div>
        <template v-else>
          <div class="mb-2 flex items-center gap-3">
            <p class="flex-1 text-[13px] text-muted-foreground">{{ $t('fieldmap.intro') }}</p>
            <span v-if="customFields.length >= MAX_CUSTOM" class="whitespace-nowrap text-xs text-[var(--ops-warning)]">
              {{ $t('device.customMax') }}
            </span>
            <Button variant="outline" size="sm" :disabled="customFields.length >= MAX_CUSTOM" @click="addCustom">
              + {{ $t('device.addCustom') }}
            </Button>
          </div>
          <div class="overflow-x-auto">
            <div class="min-w-[880px]">
              <div class="fm-row border-border font-normal text-muted-foreground text-xs" style="padding: 2px 0 6px">
                <div class="c-name">{{ $t('fieldmap.nameLabel') }}</div>
                <div class="c-mode">{{ $t('fieldmap.modeLabel') }}</div>
                <div class="c-value">{{ $t('fieldmap.valueLabel') }}</div>
                <div class="c-raw">{{ $t('fieldmap.raw') }}</div>
                <div class="c-vm">{{ $t('fieldmap.vmLabel') }}</div>
                <div class="c-preview">{{ $t('fieldmap.preview') }}</div>
                <div class="c-del" />
              </div>
              <div v-for="row in rows" :key="row.key" class="fm-row border-border/60">
                <div class="c-name" :class="{ 'font-semibold text-[13px]': !row.cf }">
                  <template v-if="row.cf">
                    <!-- 自定义字段：双语展示名可编辑；内置字段名固定不可改 -->
                    <Input v-model="row.cf.label_zh" class="h-7" :placeholder="$t('device.customNameZh')" />
                    <Input v-model="row.cf.label_en" class="h-7" :placeholder="$t('device.customNameEn')" />
                  </template>
                  <template v-else>{{ $t(`device.fields.${row.key}`) }}</template>
                </div>
                <div class="c-mode">
                  <!-- 原生 radio 自绘（替代 NRadioGroup） -->
                  <div class="flex flex-col gap-1 text-xs">
                    <label class="flex cursor-pointer items-center gap-1.5">
                      <input
                        type="radio"
                        class="accent-[var(--primary)]"
                        :name="`mode-${deviceKey}-${row.key}`"
                        :checked="(modes[row.key] ?? 'bind') === 'bind'"
                        @change="setMode(row.key, 'bind')"
                      />
                      {{ $t('fieldmap.modeBind') }}
                    </label>
                    <label class="flex cursor-pointer items-center gap-1.5">
                      <input
                        type="radio"
                        class="accent-[var(--primary)]"
                        :name="`mode-${deviceKey}-${row.key}`"
                        :checked="(modes[row.key] ?? 'bind') === 'template'"
                        @change="setMode(row.key, 'template')"
                      />
                      {{ $t('fieldmap.modeTemplate') }}
                    </label>
                  </div>
                </div>
                <div class="c-value">
                  <!-- key 绑定 deviceKey：切换实例时销毁重建，杜绝上一个 Device 的内容/高度残留 -->
                  <div v-if="(modes[row.key] ?? 'bind') === 'bind'" class="flex items-center gap-1">
                    <Select
                      :key="`b-${deviceKey}-${row.key}`"
                      :model-value="bindings[row.key] ?? ''"
                      @update:model-value="(v: string | null) => (bindings[row.key] = v || null)"
                    >
                      <SelectTrigger class="h-7" :placeholder="$t('fieldmap.selectPh')" />
                      <SelectContent>
                        <SelectItem v-for="jf in jsonFields" :key="jf" :value="jf">{{ jf }}</SelectItem>
                      </SelectContent>
                    </Select>
                    <button
                      v-if="bindings[row.key]"
                      class="flex size-5 flex-none items-center justify-center rounded text-muted-foreground hover:text-destructive"
                      :title="$t('common.delete')"
                      @click="bindings[row.key] = null"
                    >×</button>
                  </div>
                  <!-- 花括号示例是模板语法本身，必须硬编码（vue-i18n 会把 {x} 当占位符） -->
                  <div v-else>
                    <Input
                      :key="`t-${deviceKey}-${row.key}`"
                      :model-value="templates[row.key] ?? ''"
                      class="h-7"
                      :class="tplInvalid(templates[row.key]) && 'border-destructive'"
                      :placeholder="'({mapId},{areaId}) 或 ({mapId,areaId})'"
                      @update:model-value="(v: string | number) => setTpl(row.key, v)"
                    />
                    <div v-if="tplInvalid(templates[row.key])" class="text-destructive text-[11px] leading-tight">
                      {{ $t('fieldmap.tplInvalid') }}
                    </div>
                  </div>
                </div>
                <div class="c-raw mono break-all">{{ rawValue(row.key) }}</div>
                <div class="c-vm">
                  <Textarea
                    :key="`v-${deviceKey}-${row.key}`"
                    :model-value="valueMaps[row.key] ?? ''"
                    :rows="1"
                    class="min-h-0 py-0.5 text-xs"
                    :placeholder="$t('fieldmap.vmPh')"
                    @update:model-value="(v: string | number) => setVm(row.key, v)"
                  />
                </div>
                <div class="c-preview mono break-all">{{ preview(row.key) }}</div>
                <div class="c-del">
                  <Button v-if="row.cf" variant="ghost" size="sm" class="text-destructive" @click="removeCustom(row.key)">
                    {{ $t('common.delete') }}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="flex items-center gap-2.5 pt-2">
        <Button size="sm" class="bg-[var(--ops-warning)] text-white hover:opacity-90" @click="openClone">{{ $t('fieldmap.clone') }}</Button>
        <div class="flex-1" />
        <Button variant="outline" @click="emit('update:show', false)">{{ $t('common.cancel') }}</Button>
        <Button :disabled="saving" @click="save">{{ $t('fieldmap.saveMapping') }}</Button>
      </div>
    </DialogContent>
  </Dialog>

  <!-- 克隆来源选择：列出全部站点的 Device 映射配置 -->
  <Dialog v-model:open="cloneShow">
    <DialogContent class="w-[520px] max-w-[92vw]">
      <DialogHeader>
        <DialogTitle>{{ $t('fieldmap.cloneTitle') }}</DialogTitle>
      </DialogHeader>
      <p class="text-[13px] text-muted-foreground">{{ $t('fieldmap.cloneIntro') }}</p>
      <div v-if="cloneLoading" class="flex h-24 items-center justify-center">
        <div class="size-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
      </div>
      <div v-else class="max-h-[40vh] overflow-y-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border text-xs text-muted-foreground">
              <th class="w-[50px] px-2 py-1.5 text-left font-medium">{{ $t('fieldmap.pickCol') }}</th>
              <th class="w-[40%] px-2 py-1.5 text-left font-medium">{{ $t('fieldmap.siteCol') }}</th>
              <th class="px-2 py-1.5 text-left font-medium">{{ $t('fieldmap.deviceCol') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="x in cloneList"
              :key="x.site_id + '/' + x.device_id"
              class="cursor-pointer border-b border-border/60 hover:bg-accent/50"
              :class="{ 'bg-accent/50': cloneSelected === x.site_id + '/' + x.device_id }"
              @click="cloneSelected = x.site_id + '/' + x.device_id"
            >
              <td class="px-2 py-1.5">
                <input
                  type="radio"
                  class="accent-[var(--primary)]"
                  name="clone-source"
                  :checked="cloneSelected === x.site_id + '/' + x.device_id"
                  @click="cloneSelected = x.site_id + '/' + x.device_id"
                />
              </td>
              <td class="px-2 py-1.5">{{ x.site_name }}</td>
              <td class="px-2 py-1.5">{{ x.device_name }}</td>
            </tr>
            <tr v-if="!cloneList.length">
              <td colspan="3" class="py-8 text-center text-sm text-muted-foreground">{{ $t('fieldmap.noClone') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex justify-end gap-2">
        <Button variant="outline" size="sm" @click="cloneShow = false">{{ $t('common.cancel') }}</Button>
        <Button size="sm" :disabled="!cloneSelected" @click="applyClone">{{ $t('fieldmap.confirmClone') }}</Button>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.fm-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom-width: 1px;
  border-bottom-style: solid;
}
.fm-head {
  padding: 2px 0 6px;
  align-items: center;
}
.fm-row:last-of-type {
  border-bottom: none;
}
.c-name {
  width: 150px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 4px;
}
.c-mode {
  width: 112px;
  flex: none;
  padding-top: 4px;
}
.c-value {
  flex: 1.2;
  min-width: 170px;
}
.c-raw {
  width: 120px;
  flex: none;
  padding-top: 8px;
}
.c-vm {
  flex: 1;
  min-width: 150px;
}
.c-preview {
  width: 130px;
  flex: none;
  padding-top: 8px;
}
.c-del {
  width: 52px;
  flex: none;
}
.mono {
  font-size: 12px;
}
</style>
