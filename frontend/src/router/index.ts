import { createRouter, createWebHistory } from 'vue-router'
import { getModules } from '../modules'

// 模块路由由注册表生成：/console/site/:siteId/:moduleId（PRD §20.3）
const firstModule = getModules()[0]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...getModules().map((m) => ({
      path: `/console/site/:siteId/${m.routePath}`,
      component: m.view,
    })),
    { path: '/', redirect: `/console/site/demo-site/${firstModule?.routePath ?? ''}` },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
