import { defineStore } from 'pinia'

/** 三主题（顺序 = 侧栏圆点顺序）。默认 posthog。
    应用侧 = <html data-theme>，零 JS 重渲染。 */
export type OpsTheme = 'posthog' | 'holo' | 'synth'

const KEY = 'ops-theme'
const DEFAULT: OpsTheme = 'posthog'
const ALL: OpsTheme[] = ['posthog', 'holo', 'synth']

/** 历史值兼容：已删的主题（tesla/sentry/neon/mongo/旧 light）一律归到默认 posthog，
    不再按深浅猜——存了旧主题的人刷新后看到的就是默认主题。 */
const LEGACY: Record<string, OpsTheme> = {
  tesla: 'posthog',
  sentry: 'posthog',
  neon: 'posthog',
  mongo: 'posthog',
  light: 'posthog',
}

export const useThemeStore = defineStore('theme', {
  state: (): { theme: OpsTheme } => {
    const saved = localStorage.getItem(KEY)
    const theme = (saved && (saved in LEGACY ? LEGACY[saved] : saved)) as OpsTheme
    return { theme: ALL.includes(theme) ? theme : DEFAULT }
  },
  actions: {
    set(theme: OpsTheme) {
      this.theme = theme
      localStorage.setItem(KEY, theme)
    },
  },
})

/** 只有 synth 是深色（App.vue / KnowledgeViewer 按它决定二值深浅）。 */
export const DARK_THEMES: readonly OpsTheme[] = ['synth']
export const isDarkTheme = (t: OpsTheme) => DARK_THEMES.includes(t)
