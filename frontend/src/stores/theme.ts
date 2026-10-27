import { defineStore } from 'pinia'

export type OpsTheme = 'light' | 'dark'

/** 明暗二态（terminal 画风已删——等宽绿字可读性差）。默认 dark。
    历史值兼容：mono/terminal → dark。应用侧 = <html data-theme>，零 JS 重渲染。 */
const KEY = 'ops-theme'
const LEGACY: Record<string, OpsTheme> = { mono: 'dark', terminal: 'dark' }

export const useThemeStore = defineStore('theme', {
  state: (): { theme: OpsTheme } => {
    const saved = localStorage.getItem(KEY)
    const theme = (saved && (saved in LEGACY ? LEGACY[saved] : saved)) as OpsTheme
    return { theme: theme === 'light' ? 'light' : 'dark' }
  },
  actions: {
    set(theme: OpsTheme) {
      this.theme = theme
      localStorage.setItem(KEY, theme)
    },
  },
})
