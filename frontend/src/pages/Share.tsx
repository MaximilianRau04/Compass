import { useNavigate, useSearchParams } from 'react-router'

import { useTodayDate } from '../api/tasks'
import { QuickAdd } from '../components/QuickAdd'
import { useI18n } from '../i18n/context'

/** Target of the Android share sheet (Web Share Target): turns shared text or links into a task. */
export function SharePage() {
  const { t } = useI18n()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const today = useTodayDate()

  const parts = ['title', 'text', 'url'].map((key) => params.get(key)?.trim()).filter(Boolean) as string[]
  const text = [...new Set(parts)].join(' ')

  return (
    <>
      <h1 className="mb-2 font-display text-5xl leading-none font-semibold tracking-tight uppercase">{t('share.title')}</h1>
      <p className="mb-6 text-muted">{t('share.hint')}</p>
      <QuickAdd today={today} initialText={text} autoFocus onCreated={() => navigate('/')} />
    </>
  )
}
