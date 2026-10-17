import { createContext, useContext } from 'react'

import { de, en, type MessageKey } from './messages'

export type Lang = 'de' | 'en'
export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string

export const MESSAGES = { de, en }
export const LOCALES: Record<Lang, string> = { de: 'de-DE', en: 'en-GB' }
export const STORAGE_KEY = 'compass.lang'

export interface I18n {
  lang: Lang
  locale: string
  setLang: (lang: Lang) => void
  t: Translate
}

export const I18nContext = createContext<I18n | null>(null)

export function useI18n(): I18n {
  const context = useContext(I18nContext)
  if (!context) throw new Error('useI18n must be used inside I18nProvider')
  return context
}
