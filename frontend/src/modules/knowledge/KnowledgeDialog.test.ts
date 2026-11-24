// @vitest-environment happy-dom
import axios from 'axios'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeDialog from './KnowledgeDialog.vue'
import { i18n, setLocale } from '../../i18n'

/** 拦截 knowledgeApi.create：测试自己驱动进度回调与 abort，不真发请求 */
const { createMock } = vi.hoisted(() => ({ createMock: vi.fn() }))
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, knowledgeApi: { ...actual.knowledgeApi, create: createMock } }
})

type Pending = {
  opts: { onProgress?: (loaded: number, total: number) => void; signal?: AbortSignal }
  resolve: (v: unknown) => void
  reject: (e: unknown) => void
}
let pending: Pending | null = null

beforeEach(() => {
  setLocale('en') // 组件文案已迁移 i18n；断言基于英文
  pending = null
  createMock.mockReset()
  createMock.mockImplementation((_site, _file, _name, _desc, opts: Pending['opts']) =>
    new Promise((resolve, reject) => {
      pending = { opts, resolve, reject }
    }),
  )
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

let wrapper: ReturnType<typeof mount> | null = null

/** Dialog 经 Portal 渲染到 body：一切查询都走 document.body */
function body(): HTMLElement {
  return document.body
}
function bodyButtons(): HTMLButtonElement[] {
  return [...body().querySelectorAll('button')]
}

async function open(): Promise<void> {
  wrapper = mount(KnowledgeDialog, {
    props: { show: true, siteId: 's1', siteName: 'Site A', editing: null, docs: [] },
    global: { plugins: [i18n] },
  })
  await flushPromises()
}

/** 把文件塞进隐藏的 file input 并触发 change（组件的 onPick 读 e.target.files） */
async function pickFile(name: string, bytes: number): Promise<void> {
  const input = body().querySelector('input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', {
    configurable: true,
    value: [new File([new Uint8Array(bytes)], name)],
  })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
}

function clickButton(text: string): void {
  const btn = bodyButtons().find((b) => b.textContent?.trim() === text)
  expect(btn, `button "${text}" should exist`).toBeDefined()
  btn!.click()
}

function progressText(): string {
  return body().textContent ?? ''
}

describe('KnowledgeDialog 上传进度与取消', () => {
  it('上传中显示确定性进度（百分比 + 已传/总量），100% 后关弹窗并发 saved', async () => {
    await open()
    await pickFile('nginx.conf', 2048)
    clickButton('Upload')
    await flushPromises()

    expect(pending, 'create should have been called').not.toBeNull()
    pending!.opts.onProgress?.(1024, 2048)
    await flushPromises()
    expect(progressText()).toContain('50%')
    expect(progressText()).toContain('1.0 KB')
    // 进度条真的渲染出来了（不是只有文字）
    expect(body().querySelector('[role="status"]')).not.toBeNull()

    pending!.opts.onProgress?.(2048, 2048)
    pending!.resolve({ id: 'd1' })
    await flushPromises()

    expect(wrapper!.emitted('saved')).toHaveLength(1)
    expect(wrapper!.emitted('update:show')?.at(-1)).toEqual([false])
  })

  it('取消会中止请求（signal abort）并关闭弹窗', async () => {
    await open()
    await pickFile('big.bin', 4096)
    clickButton('Upload')
    await flushPromises()

    const signal = pending!.opts.signal
    expect(signal, 'upload should pass an AbortSignal').toBeDefined()
    expect(signal!.aborted).toBe(false)

    // 取消 = 中断上传 + 关弹窗（与右上角 X 同一出口）
    clickButton('Cancel')
    expect(signal!.aborted).toBe(true)

    // 后端/axios 因 abort 抛取消错误 —— 组件走 isCancel 分支，不当成红色报错
    pending!.reject(new axios.CanceledError('canceled'))
    await flushPromises()

    expect(wrapper!.emitted('update:show')?.at(-1)).toEqual([false])
  })

  it('上传中锁住表单：换文件/改名的入口都不可点', async () => {
    await open()
    await pickFile('a.txt', 10)
    clickButton('Upload')
    await flushPromises()

    pending!.opts.onProgress?.(5, 10)
    await flushPromises()

    const removeFile = bodyButtons().find((b) => b.querySelector('svg.lucide-x'))
    expect(removeFile?.disabled).toBe(true)
    // 除 file input 外的输入框（站点/名称/描述）都应禁用；站点那个本来就恒禁用，
    // 所以断言「名称」这一个真正被锁的
    const inputs = [...body().querySelectorAll('input')].filter((i) => i.type !== 'file')
    expect(inputs.map((i) => i.disabled)).toEqual([true, true, true])
  })
})
