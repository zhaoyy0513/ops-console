// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CountdownConfirm from './CountdownConfirm.vue'
import { i18n, setLocale } from '../i18n'

beforeEach(() => {
  vi.useFakeTimers()
  setLocale('en') // 组件文案已迁移 i18n；断言基于英文
})
afterEach(() => vi.useRealTimers())

describe('CountdownConfirm', () => {
  async function open(seconds = 5, onConfirm?: () => Promise<unknown>) {
    const wrapper = mount(CountdownConfirm, {
      props: { label: 'Delete', target: 'device:001', seconds, onConfirm },
      global: { plugins: [i18n], stubs: { teleport: true } },
    })
    await wrapper.find('button').trigger('click') // 打开确认框
    return wrapper
  }

  it('disables confirm during countdown, calls onConfirm once, and guards double-click', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const wrapper = await open(5, onConfirm)
    // 打开即开始倒计时，初始禁点（PRD §11.5）
    const buttons = wrapper.findAll('button').filter((b) => b.text() === 'Delete' && !b.text().includes('wait'))
    const modalConfirm = buttons.at(-1)!
    expect(modalConfirm.attributes('disabled')).toBeDefined()

    await vi.advanceTimersByTimeAsync(5000)
    expect(modalConfirm.attributes('disabled')).toBeUndefined()

    await modalConfirm.trigger('click')
    await modalConfirm.trigger('click') // pending 期间连点应被忽略（in-flight 保护）
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows remaining seconds text', async () => {
    const wrapper = await open(5)
    expect(wrapper.text()).toContain('Please wait 5s...')
  })
})
