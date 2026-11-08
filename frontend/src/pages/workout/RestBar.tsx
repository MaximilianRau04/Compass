import { useEffect, useRef } from 'react'

import { useI18n } from '../../i18n/context'
import { button } from '../../lib/ui'
import { clock, type RestTimer } from '../../lib/workout'
import { beep } from './hooks'

export function RestBar({ rest, now, onChange }: { rest: RestTimer; now: number; onChange: (r: RestTimer | null) => void }) {
  const { t } = useI18n()
  // `now` ticks once a second, so right after the start it can lag behind: never above the full rest.
  const left = Math.min(rest.seconds, Math.ceil((new Date(rest.ends_at).getTime() - now) / 1000))
  const over = left <= 0
  const alerted = useRef<string | null>(null)

  // Once per rest: vibrate, beep and, with the phone in the pocket, a notification.
  useEffect(() => {
    if (!over || alerted.current === rest.ends_at) return
    alerted.current = rest.ends_at
    // Back on the page long after the end (reload, phone in the pocket): no alarm any more.
    if (left < -60) return
    navigator.vibrate?.([250, 120, 250])
    beep()
    if (document.visibilityState === 'hidden' && 'Notification' in window && Notification.permission === 'granted') {
      void navigator.serviceWorker?.ready
        .then((r) => r.showNotification(t('log.restOver'), { body: t('log.restNext', { name: rest.next }), tag: 'compass-rest', silent: false }))
        .catch(() => undefined)
    }
  }, [over, left, rest, t])

  // A few seconds after the end it gets out of the way.
  useEffect(() => {
    if (left > -8) return
    onChange(null)
  }, [left, onChange])

  const shift = (by: number) => {
    const ends = Math.max(now, new Date(rest.ends_at).getTime()) + by * 1000
    onChange({ ...rest, ends_at: new Date(Math.max(now + 1000, ends)).toISOString(), seconds: Math.max(1, rest.seconds + by) })
  }
  const progress = over ? 1 : Math.min(1, Math.max(0, 1 - left / rest.seconds))

  return (
    <div
      role="timer"
      aria-live={over ? 'assertive' : 'off'}
      className="fixed inset-x-3 bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-20 mx-auto max-w-xl overflow-hidden rounded-xl border border-rule bg-paper-raised/95 shadow-lg backdrop-blur sm:bottom-6"
    >
      <div className="h-1 bg-rule">
        <div className={`h-1 transition-[width] duration-1000 ease-linear ${over ? 'bg-brass' : 'bg-chart'}`} style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="flex items-center gap-3 px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <p className={`font-mono text-2xs tracking-wider uppercase ${over ? 'text-brass' : 'text-muted'}`}>{over ? t('log.restOver') : t('log.rest')}</p>
          <p className="truncate text-sm text-muted">{t('log.restNext', { name: rest.next })}</p>
        </div>
        <span className={`font-mono text-3xl font-medium tabular-nums ${over ? 'text-brass' : ''}`}>{over ? '0:00' : clock(left)}</span>
        {!over && (
          <>
            <button type="button" onClick={() => shift(-15)} aria-label={t('log.restLess')} className={button('secondary', 'sm')}>
              −15
            </button>
            <button type="button" onClick={() => shift(15)} aria-label={t('log.restMore')} className={button('secondary', 'sm')}>
              +15
            </button>
          </>
        )}
        <button type="button" onClick={() => onChange(null)} className={button(over ? 'primary' : 'quiet', 'sm')}>
          {over ? t('log.restDone') : t('log.restSkip')}
        </button>
      </div>
    </div>
  )
}
