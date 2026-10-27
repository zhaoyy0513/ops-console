// @vitest-environment happy-dom
// 回归：DiffJsonEditor 的删除（含跨换行/空白）必须真实生效且不被受控环弹回。
// 源起用户反馈"换行后空白删不掉"——三条路径实测均正常（2026-10-27 复核；
// 过程中 agent 曾写错用例 2 的期望位置，已按真实删除语义修正）。
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EditorView } from 'codemirror'
import { i18n } from '../../i18n'
import { useSiteStore } from '../../stores/site'

vi.mock('@/lib/message', () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }))

// 多行带缩进 JSON（用户场景：值里有换行）
let stored = '{\n  "a": 1,\n  "b": 2\n}'

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
  operate: vi.fn().mockResolvedValue({ success: true, latency_ms: 1 }),
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

function bView(): EditorView {
  const dom = document.querySelector('.cm-merge-b')!
  const v = EditorView.findFromDOM(dom as HTMLElement)
  expect(v).toBeTruthy()
  return v!
}

async function settle() {
  await flushPromises()
  await new Promise((r) => setTimeout(r, 30))
  await flushPromises()
}

describe('DiffJsonEditor deletion sticks', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    stored = '{\n  "a": 1,\n  "b": 2\n}'
  })

  it('backspace at end of line 1 deletes the newline (doc really changes)', async () => {
    const w = await boot()
    const b = bView()
    expect(b.state.doc.toString()).toBe(stored)

    // 光标放行 1 尾（换行符前），按一次 Backspace
    const pos = b.state.doc.line(1).to
    b.dispatch({ selection: { anchor: pos } })
    b.focus()
    b.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true }))
    await settle()

    const after = b.state.doc.toString()
    console.log('doc after keydown backspace:', JSON.stringify(after))
    expect(after).not.toBe(stored)

    // 受控环：父组件 editText 回灌后文档应保持已删除状态（不被弹回）
    await settle()
    const settled = b.state.doc.toString()
    console.log('doc after loop settle  :', JSON.stringify(settled))
    console.log('parent modelValue      :', JSON.stringify(w.getComponent(DiffJsonEditor).props('modelValue')))
    expect(settled).toBe(after)
    w.unmount()
  })

  it('direct dispatch deletion (pure controlled-loop path) also sticks', async () => {
    const w = await boot()
    const b = bView()
    const pos = b.state.doc.line(1).to
    b.dispatch({ selection: { anchor: pos }, changes: { from: pos, to: pos + 1, insert: '' } })
    await settle()
    await settle()
    const after = b.state.doc.toString()
    console.log('doc after dispatch     :', JSON.stringify(after))
    // 删掉 { 后的换行符：缩进保留、换行消失，且删除稳定不被受控环弹回
    expect(after).toBe('{  "a": 1,\n  "b": 2\n}')
    w.unmount()
  })

  it('backspace deleting only whitespace sticks too', async () => {
    const w = await boot()
    const b = bView()
    // 行 2 开头的缩进：光标放行首按 Backspace（应删掉前面的换行/空格）
    const l2 = b.state.doc.line(2)
    b.dispatch({ selection: { anchor: l2.from } })
    b.focus()
    b.contentDOM.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true }))
    await settle()
    const after = b.state.doc.toString()
    console.log('doc after ws backspace :', JSON.stringify(after))
    expect(after.length).toBeLessThan(stored.length)
    w.unmount()
  })
})
