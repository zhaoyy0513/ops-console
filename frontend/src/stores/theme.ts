import { defineStore } from 'pinia'

export type OpsTheme = 'neon' | 'holo' | 'synth'

/** 三主题（neon 深色霓虹 / holo 全息幻彩浅色 / synth 复古落日），默认 neon。
    历史值兼容：mono/terminal/dark → neon，light → holo。应用侧 = <html data-theme>，零 JS 重渲染。 */
const KEY = 'ops-theme'
const LEGACY: Record<string, OpsTheme> = { mono: 'neon', terminal: 'neon', dark: 'neon', light: 'holo' }
const ALL: OpsTheme[] = ['neon', 'holo', 'synth']

export const useThemeStore = defineStore('theme', {
  state: (): { theme: OpsTheme } => {
    const saved = localStorage.getItem(KEY)
    const theme = (saved && (saved in LEGACY ? LEGACY[saved] : saved)) as OpsTheme
    return { theme: ALL.includes(theme) ? theme : 'neon' }
  },
  actions: {
    set(theme: OpsTheme) {
      this.theme = theme
      localStorage.setItem(KEY, theme)
    },
  },
})
