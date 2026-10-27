import { toast as vueSonner } from 'vue-sonner'

/** 全站 toast 单一入口：useMessage 迁移替身。
    API 与 naive useMessage 的常用子集对齐（success/error/info/warning + 文本入参）。 */
export const message = {
  success: (content: string) => void vueSonner.success(content),
  error: (content: string) => void vueSonner.error(content),
  warning: (content: string) => void vueSonner.warning(content),
  info: (content: string) => void vueSonner.info(content),
}
