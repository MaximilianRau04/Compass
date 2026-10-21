import { useState } from 'react'

import { useI18n } from '../i18n/context'
import { clockTime, localDay, relativeDay } from '../lib/format'

// News feeds and university servers fail for an hour now and then; only a longer outage is an error.
const STALE_MS = 12 * 60 * 60 * 1000

/** A failed fetch of one source: calm while it worked recently, red once it keeps failing. */
export function SyncIssue({ name, error, lastSuccess, today }: { name: string; error: string; lastSuccess: string | null; today: string }) {
  const { t, locale } = useI18n()
  const [now] = useState(() => Date.now())
  const stale = !lastSuccess || now - new Date(lastSuccess).getTime() > STALE_MS
  const when = lastSuccess ? `${relativeDay(localDay(lastSuccess), today, t, locale)} ${clockTime(lastSuccess, locale)}` : t('sync.never')
  return <p className={stale ? 'text-signal' : 'text-muted'}>{t(stale ? 'sync.failing' : 'sync.hiccup', { name, error, when })}</p>
}
