// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CountdownConfirm from './CountdownConfirm.vue'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('CountdownConfirm', () => {
  async function open(seconds = 5) {
    const wrapper = mount(CountdownConfirm, {
      props: { label: 'Delete', target: 'robot:001', seconds },
      global: { stubs: { teleport: true } },
    })
    await wrapper.find('button').trigger('click') // 打开确认框
    return wrapper
  }

  it('disables confirm during countdown and emits after expiry', async () => {
    const wrapper = await open(5)
    // 打开即开始倒计时，初始禁点（PRD §11.5）
    let buttons = wrapper.findAll('button').filter((b) => b.text() === 'Delete' && !b.text().includes('wait'))
    const modalConfirm = buttons.at(-1)!
    expect(modalConfirm.attributes('disabled')).toBeDefined()

    await vi.advanceTimersByTimeAsync(5000)
    expect(modalConfirm.attributes('disabled')).toBeUndefined()

    await modalConfirm.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('shows remaining seconds text', async () => {
    const wrapper = await open(5)
    expect(wrapper.text()).toContain('Please wait 5s...')
  })
})
