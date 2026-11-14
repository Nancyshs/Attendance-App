import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/**
 * Bilingual UI: Arabic (RTL, default) and English (LTR).
 * `t(en, ar)` returns the text for the active language. Non-React code can use `tr()` / `getLang()`.
 */
export type Lang = 'ar' | 'en'

const KEY = 'lang'
// The programme is Arabic only. A previously saved English choice is ignored.
let current: Lang = 'ar'

export const getLang = (): Lang => 'ar'
export const tr = (en: string, ar: string): string => (current === 'ar' ? ar : en)

interface I18n {
  lang: Lang
  dir: 'ltr' | 'rtl'
  /** Inline bilingual text: t('Save', 'حفظ'). */
  t: (en: string, ar: string) => string
  setLang: (l: Lang) => void
  toggle: () => void
}

const Ctx = createContext<I18n | null>(null)

function apply(lang: Lang) {
  current = 'ar'
  lang = 'ar'
  document.documentElement.lang = 'ar'
  document.documentElement.dir = 'rtl'
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    /* private mode */
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current)
  useEffect(() => apply(lang), [lang])

  const setLang = useCallback((l: Lang) => {
    apply(l) // update synchronously so non-React helpers (api, format) already use the new language
    setLangState(l)
  }, [])
  const t = useCallback((en: string, ar: string) => (lang === 'ar' ? ar : en), [lang])
  const toggle = useCallback(() => setLang(current === 'ar' ? 'en' : 'ar'), [setLang])
  const value = useMemo<I18n>(() => ({ lang, dir: lang === 'ar' ? 'rtl' : 'ltr', t, setLang, toggle }), [lang, t, setLang, toggle])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const v = useContext(Ctx)
  if (!v) throw new Error('I18nProvider missing')
  return v
}
