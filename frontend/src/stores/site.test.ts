// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listMock } = vi.hoisted(() => ({ listMock: vi.fn() }))
vi.mock('../modules/sites/api', () => ({
  sitesApi: { list: listMock },
}))

import { useSiteStore } from './site'

describe('site store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listMock.mockReset()
  })

  it('switcher options exclude disabled sites', async () => {
    listMock.mockResolvedValue([
      { id: 'a', name: 'A', enabled: true },
      { id: 'b', name: 'B', enabled: false },
    ])
    const store = useSiteStore()
    await store.loadSites()
    expect(store.options).toEqual([{ label: 'A', value: 'a' }])
    expect(store.sites).toHaveLength(2) // 管理页仍能看到停用站点
  })

  it('clears current selection when it gets disabled or removed', async () => {
    listMock.mockResolvedValue([
      { id: 'a', name: 'A', enabled: true },
      { id: 'b', name: 'B', enabled: true },
    ])
    const store = useSiteStore()
    await store.loadSites()
    store.setSite('a')

    // 停用当前站点 -> 下拉置空（联动菜单置灰）
    store.sites = store.sites.map((s) => (s.id === 'a' ? { ...s, enabled: false } : s))
    await Promise.resolve() // flush watch
    expect(store.currentSiteId).toBe('')
    expect(store.options.map((o) => o.value)).toEqual(['b']) // 下拉只剩启用的

    // 删除当前站点同样置空
    store.setSite('b')
    store.sites = store.sites.filter((s) => s.id !== 'b')
    await Promise.resolve()
    expect(store.currentSiteId).toBe('')
  })

  it('currentSite resolves only from full site list', async () => {
    listMock.mockResolvedValue([{ id: 'a', name: 'A', enabled: true }])
    const store = useSiteStore()
    await store.loadSites()
    store.setSite('a')
    expect(store.currentSite?.name).toBe('A')
    store.setSite('nope')
    expect(store.currentSite).toBeNull()
  })
})
