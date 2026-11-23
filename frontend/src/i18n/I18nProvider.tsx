import { useCallback, useEffect, useMemo, useState } from 'react'

import { I18nContext, type Lang, LOCALES, MESSAGES, STORAGE_KEY, type Translate } from './context'
import { formatMessage } from './format'

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'de' || stored === 'en') return stored
  } catch {
    // Storage can be unavailable (private mode); fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith('de') ? 'de' : 'en'
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Not persisted; the choice still applies for this session.
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const t = useCallback<Translate>(
    (key, vars) => formatMessage(MESSAGES[lang][key], vars),
    [lang],
  )

  const value = useMemo(() => ({ lang, locale: LOCALES[lang], setLang, t }), [lang, setLang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
