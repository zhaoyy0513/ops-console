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
