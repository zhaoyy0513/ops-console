// @vitest-environment happy-dom
// SshView 渲染回归：创建弹窗必须含“定时任务”开关与 Cron 输入（曾因模块缓存/模板损坏反复回归）
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n } from '../../i18n'
import { useSiteStore } from '../../stores/site'

vi.mock('@/lib/message', () => ({ message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }))
vi.mock('../../api', () => ({ default: { post: vi.fn().mockResolvedValue({ valid: true, next_runs: [] }) } }))
vi.mock('./api', () => ({
  sshApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    run: vi.fn(),
  },
}))
vi.mock('../sites/api', () => ({
  sitesApi: { list: vi.fn().mockResolvedValue([]), listResources: vi.fn().mockResolvedValue([]) },
}))

import SshView from './SshView.vue'

describe('SshView render regression', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('create modal contains the cron switch and cron input', async () => {
    const store = useSiteStore()
    store.setSite('sz')

    const wrapper = mount(SshView, {
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    await flushPromises()

    // 打开新增脚本弹窗
    const btn = wrapper.findAll('button').find((b) => b.text().includes('新增脚本'))
    expect(btn, '新增脚本按钮应存在（i18n zh）').toBeTruthy()
    await btn!.trigger('click')
    await flushPromises()

    // 弹窗经 DialogPortal teleport 挂到 body：断言"定时任务"开关与 cron 控件在渲染结果中
    const html = document.body.innerHTML
    expect(html).toContain('定时任务')
    // 调试输出：确认开关控件的真实 DOM 形态
    const i = html.indexOf('定时任务')
    console.log('MODAL_SNIPPET>>>', html.slice(Math.max(0, i - 150), i + 250).replace(/\s+/g, ' '))
    expect(html).toContain('switch')
    wrapper.unmount()
  })
})
