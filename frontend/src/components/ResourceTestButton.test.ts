// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ResourceTestButton from './ResourceTestButton.vue'

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }))
vi.mock('../api', () => ({ default: { post: postMock } }))

async function mounted(result: unknown) {
  postMock.mockResolvedValueOnce(result)
  const wrapper = mount(ResourceTestButton, {
    props: { type: 'redis', config: { host: '10.0.0.1', password: 'x' } },
  })
  await wrapper.find('button').trigger('click')
  await flushPromises()
  return wrapper
}

describe('ResourceTestButton', () => {
  it('posts type+config and renders success state', async () => {
    const wrapper = await mounted({ success: true, latency_ms: 42, message: 'Connected, Redis 7.2.4' })
    expect(postMock).toHaveBeenCalledWith('/test-connection', {
      type: 'redis',
      config: { host: '10.0.0.1', password: 'x' },
    })
    expect(wrapper.text()).toContain('OK')
    expect(wrapper.text()).toContain('42ms')
  })

  it('renders failure state', async () => {
    const wrapper = await mounted({ success: false, latency_ms: 3002, message: 'Connection timed out after 3s' })
    expect(wrapper.text()).toContain('FAILED')
    expect(wrapper.text()).toContain('timed out')
  })

  it('renders failure on network error', async () => {
    postMock.mockRejectedValueOnce(new Error('Network Error'))
    const wrapper = mount(ResourceTestButton, { props: { type: 'mq', config: {} } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('FAILED')
    expect(wrapper.text()).toContain('Network Error')
  })
})
