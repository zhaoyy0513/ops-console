// @vitest-environment happy-dom
// 回归：保存拦截曾两度失灵——(1) locateJsonError 里 lezer 容错解析从不抛错导致恒返回 ''（falsy），
// jsonInvalid 永远拦不住；(2) jsonInvalid 只看 format，JSON 值的 key 在 Text 视图改坏静默写回。
// 另覆盖：保存成功后 diff 双栏仍在且无变更高亮（曾随静默写坏 JSON 后 format 回退成单栏 textarea）。
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { useSiteStore } from '../../stores/site'

vi.mock('@/lib/message', () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }))
import { message } from '@/lib/message'

let stored = '{\n  "a": 1\n}'
const operateMock = vi.fn().mockImplementation((_s: string, _i: string, body: { op: string; type?: string; value?: unknown }) => {
  if (body.op === 'set' && body.type === 'string') stored = String(body.value)
  return Promise.resolve({ success: true, latency_ms: 1 })
})

vi.mock('./api', () => ({
  getInfo: vi.fn().mockResolvedValue({
    status: 'ok', version: '7', uptime_seconds: 1, memory_used: 1, memory_peak: 1,
    memory_fragmentation: 1, connected_clients: 1, commands_per_sec: 1,
    total_commands_processed: 1, hit_rate: 1, evicted_keys: 0, expired_keys: 0,
    db_size: 1, db_sizes: {},
  }),
  listKeys: vi.fn().mockResolvedValue({ keys: [{ key: 'jk', type: 'string' }], cursor: 0, count: 1 }),
  getKey: vi.fn().mockImplementation(async () => ({
    key: 'jk', type: 'string', ttl: -1, memory_usage: 16, value: stored,
  })),
  operate: (...args: unknown[]) => operateMock(...(args as [string, string, never])),
}))
vi.mock('../sites/api', () => ({
  sitesApi: { list: vi.fn().mockResolvedValue([]), listResources: vi.fn().mockResolvedValue([{ id: 'r1', name: 'r1' }]) },
}))

import RedisView from './RedisView.vue'
import DiffJsonEditor from '../../components/DiffJsonEditor.vue'

async function boot() {
  const store = useSiteStore()
  store.setSite('sz')
  const wrapper = mount(
    RedisView,
    { global: { plugins: [i18n] }, attachTo: document.body, provide: { opsTheme: computed<'light' | 'mono' | 'terminal'>(() => 'mono') } },
  )
  await flushPromises()
  const leaf = wrapper.findAll('.tree-leaf').find((n) => n.text().includes('jk'))
  await leaf!.trigger('click')
  await flushPromises()
  return wrapper
}

function btn(text: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent!.replace(/\s/g, '').includes(text))
}

describe('RedisView save validation regression', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    stored = '{\n  "a": 1\n}'
    operateMock.mockClear()
    vi.mocked(message.error).mockClear()
  })

  it('Json 视图语法错误：保存被拦（不弹确认框）+ 错误横幅 + toast', async () => {
    const w = await boot()
    expect(w.findAll('.cm-editor').length).toBe(2)
    w.getComponent(DiffJsonEditor).vm.$emit('update:modelValue', '{\n  "a": 1,,\n}')
    await flushPromises()
    expect(w.find('.json-banner').exists()).toBe(true) // 红色横幅（含行/列定位）
    btn('保存')!.click()
    await flushPromises()
    expect(document.body.textContent).not.toContain('写入 Key') // 未开确认框
    expect(message.error).toHaveBeenCalled() // toast（lib 函数，不依赖组件树）
    expect(operateMock).not.toHaveBeenCalled()
    w.unmount()
  })

  it('Text 视图改坏 JSON 值（loadedAsJson 基线）：同样拦下，不静默写坏', async () => {
    const w = await boot()
    await w.findAll('.fmt-btn').find((l) => l.text() === 'Text')!.trigger('click')
    await flushPromises()
    await w.find('textarea').setValue('{\n  "a": 1,,\n}')
    btn('保存')!.click()
    await flushPromises()
    expect(document.body.textContent).not.toContain('写入 Key')
    expect(message.error).toHaveBeenCalled()
    expect(operateMock).not.toHaveBeenCalled()
    expect(stored).toBe('{\n  "a": 1\n}') // Redis 里的值未被写坏
    w.unmount()
  })

  it('合法保存后：diff 双栏仍在、无变更高亮、值已写入', async () => {
    const w = await boot()
    w.getComponent(DiffJsonEditor).vm.$emit('update:modelValue', '{\n  "a": 2\n}')
    await flushPromises()
    btn('保存')!.click()
    await flushPromises()
    btn('确认写入')!.click()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))
    expect(w.findAll('.cm-editor').length).toBe(2) // 左=已存新值，右=同值
    expect(w.findAll('.cm-changedLine').length).toBe(0) // 无 diff 高亮
    expect(stored).toContain('"a": 2')
    w.unmount()
  })
})
