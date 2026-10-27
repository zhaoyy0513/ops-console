import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { sitesApi, type Site } from '../modules/sites/api'

/**
 * Site Context（PRD §21）：当前站点 + 站点列表（顶栏下拉与站点管理页共享，
 * 任一处增删后 loadSites() 刷新，两处自动同步）。
 */
export const useSiteStore = defineStore('site', () => {
  const currentSiteId = ref('')
  const sites = ref<Site[]>([])
  // 首次 loadSites 是否已完成：ensureValidSite 用它区分"列表为空"与"列表未就绪"，
  // 否则整页直达 /console 链接时会在列表返回前误判站点无效而被弹回 /sites（竞态）
  const loaded = ref(false)

  const currentSite = computed(
    () => sites.value.find((s) => s.id === currentSiteId.value) ?? null,
  )
  // 下拉只列启用的站点；停用的（含正在浏览的）由守卫踢出
  const options = computed(() =>
    sites.value.filter((s) => s.enabled).map((s) => ({ label: s.name, value: s.id })),
  )

  function setSite(id: string) {
    currentSiteId.value = id
  }

  // currentSiteId 必须始终指向启用站点：停用/删除当前站点后立即置空——
  // 下拉框归零，联动侧栏菜单置灰（下拉框是主驱动）
  watch(sites, (list) => {
    if (currentSiteId.value && !list.some((s) => s.enabled && s.id === currentSiteId.value)) {
      currentSiteId.value = ''
    }
  })

  async function loadSites() {
    try {
      sites.value = await sitesApi.list()
    } catch {
      // 后端未就绪时保留现状，不阻塞页面
    } finally {
      loaded.value = true
    }
  }

  return { currentSiteId, currentSite, sites, options, loaded, setSite, loadSites }
})
