import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * Site Context（PRD §21）：当前站点全局状态。
 * 模块内 watch 路由参数或 store 变化自行重载。
 */
export const useSiteStore = defineStore('site', () => {
  const currentSiteId = ref('')
  // 完整站点对象（name/description 等）在 T06 站点 API 落地后填充
  const currentSite = computed(() =>
    currentSiteId.value ? { id: currentSiteId.value } : null,
  )

  function setSite(id: string) {
    currentSiteId.value = id
  }

  return { currentSiteId, currentSite, setSite }
})
