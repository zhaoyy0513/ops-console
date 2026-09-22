import { createRouter, createWebHistory } from 'vue-router'
import { getModules } from '../modules'
import SitesView from '../modules/sites/SitesView.vue'
import AuditView from '../modules/overview/AuditView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/sites', component: SitesView }, // 站点管理（站点上下文之外的全局页）
    { path: '/audit', component: AuditView }, // 操作日志（全局页）
    ...getModules().map((m) => ({
      path: `/console/site/:siteId/${m.routePath}`,
      component: m.view,
    })),
    { path: '/', redirect: '/sites' }, // 先见站点管理（无占位站点；MainLayout 会自动跳第一个真实站点）
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
