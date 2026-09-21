import { createRouter, createWebHistory } from 'vue-router'
import { getModules } from '../modules'
import SitesView from '../modules/sites/SitesView.vue'

// 模块路由由注册表生成：/console/site/:siteId/:moduleId（PRD §20.3）
const firstModule = getModules()[0]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/sites', component: SitesView }, // 站点管理（站点上下文之外的全局页）
    ...getModules().map((m) => ({
      path: `/console/site/:siteId/${m.routePath}`,
      component: m.view,
    })),
    { path: '/', redirect: `/console/site/demo-site/${firstModule?.routePath ?? ''}` },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
