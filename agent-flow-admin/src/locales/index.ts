import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export const LOCALE_KEY = 'af-lang'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const
export type Locale = (typeof SUPPORTED_LOCALES)[number]

export function getInitialLocale(): Locale {
  const saved = localStorage.getItem(LOCALE_KEY) as Locale | null
  return saved && SUPPORTED_LOCALES.includes(saved) ? saved : 'zh-CN'
}

const i18n = createI18n({
  legacy: false,
  locale: getInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  }
})

export default i18n
