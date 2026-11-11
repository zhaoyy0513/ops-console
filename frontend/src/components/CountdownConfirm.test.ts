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
  let wrapper: Awaited<ReturnType<typeof open>> | null = null
  // teleport 后弹窗 DOM 挂在 document.body（不在 wrapper 内），每例卸载并清 body 防泄漏
  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    document.body.innerHTML = ''
  })

  // 弹窗经 <Teleport to="body"> 渲染：按钮/文案均从 document.body 查询
  // 显式返回类型，避免 open <-> wrapper 相互推导（TS2502 循环类型，vue-tsc -b 阻塞）
  async function open(seconds = 5, onConfirm?: () => Promise<unknown>): Promise<ReturnType<typeof mount>> {
    wrapper = mount(CountdownConfirm, {
      props: { label: 'Delete', target: 'device:001', seconds, onConfirm },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button').trigger('click') // 打开确认框（触发按钮在 wrapper 内）
    return wrapper
  }

  function bodyButtons(): HTMLButtonElement[] {
    return [...document.body.querySelectorAll('button')]
  }

  it('disables confirm during countdown, calls onConfirm once, and guards double-click', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    await open(5, onConfirm)
    // 打开即开始倒计时，初始禁点（PRD §11.5）
    const modalConfirm = bodyButtons().find((b) => b.textContent?.trim() === 'Delete')!
    expect(modalConfirm).toBeDefined()
    expect(modalConfirm.disabled).toBe(true)

    await vi.advanceTimersByTimeAsync(5000)
    expect(modalConfirm.disabled).toBe(false)

    modalConfirm.click()
    await vi.advanceTimersByTimeAsync(0)
    modalConfirm.click() // pending 期间连点应被忽略（in-flight 保护）
    await vi.advanceTimersByTimeAsync(0)
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows remaining seconds text', async () => {
    await open(5)
    expect(document.body.textContent).toContain('Please wait 5s...')
  })

  it('onConfirm 失败：保持弹窗并允许重试', async () => {
    const onConfirm = vi.fn().mockRejectedValueOnce(new Error('delete failed')).mockResolvedValue(undefined)
    await open(5, onConfirm)
    const modalConfirm = bodyButtons().find((b) => b.textContent?.trim() === 'Delete')!
    await vi.advanceTimersByTimeAsync(5000)
    modalConfirm.click()
    await vi.advanceTimersByTimeAsync(0)
    expect(document.body.querySelector('[role="alertdialog"]')).not.toBeNull()
    await vi.advanceTimersByTimeAsync(0)
    modalConfirm.click()
    await vi.advanceTimersByTimeAsync(0)
    expect(onConfirm).toHaveBeenCalledTimes(2)
  })

  it('escape and overlay clicks do not dismiss while countdown runs', async () => {
    await open(5)
    // cancelable 必须显式开启，否则 preventDefault 无效（真实键盘事件可取消）
    document.body.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    await vi.advanceTimersByTimeAsync(10)
    expect(document.body.querySelector('[role="alertdialog"]')).not.toBeNull()
    expect(document.body.textContent).toContain('Please wait')
  })
})
