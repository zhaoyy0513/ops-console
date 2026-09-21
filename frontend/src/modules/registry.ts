import type { Component } from 'vue'

/**
 * 前端模块契约（PRD §20.2）。
 * 新增模块：新建 modules/<id>/ 目录，index.ts 里 defineOpsModule({...})，
 * 再在 modules/index.ts 加一行 import —— layout / router 零改动。
 */
export interface OpsModule {
  id: string
  title: string
  order: number
  icon: string // ionicons 图标名，图标渲染后续接入
  routePath: string // 挂在 /console/site/:siteId/ 下
  view: Component
}

const registered: OpsModule[] = []

export function defineOpsModule(module: OpsModule): OpsModule {
  registered.push(module)
  return module
}

export function getModules(): OpsModule[] {
  return [...registered].sort((a, b) => a.order - b.order)
}
