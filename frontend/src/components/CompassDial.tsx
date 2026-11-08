import { useEffect, useState } from 'react'

import { useI18n } from '../i18n/context'

/**
 * The day's bearing: the needle turns clockwise as tasks get done.
 * North (0°) = nothing done yet, a full turn = everything for today is done.
 */
export function CompassDial({ done, total }: { done: number; total: number }) {
  const { t } = useI18n()
  const ratio = total === 0 ? 0 : done / total
  const angle = Math.round(ratio * 360)
  const complete = total > 0 && done >= total
  const ticks = Array.from({ length: 36 }, (_, i) => i * 10)
  // The needle starts at north and swings to the day's bearing once the page is up.
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    const frame = requestAnimationFrame(() => setSettled(true))
    return () => cancelAnimationFrame(frame)
  }, [])
  const shown = settled ? angle : 0

  return (
    <figure className="flex items-center gap-3" aria-label={t('dial.label', { done, total })}>
      <svg viewBox="-60 -60 120 120" className="h-20 w-20 shrink-0 sm:h-24 sm:w-24" role="img" aria-hidden>
        <circle r="52" className="fill-paper-raised stroke-rule" strokeWidth="1.5" />
        {complete && <circle key={done} r="52" className="ping fill-none stroke-sea" strokeWidth="2" />}
        {ticks.map((deg) => (
          <line
            key={deg}
            x1="0"
            y1={deg % 90 === 0 ? -52 : -52}
            x2="0"
            y2={deg % 90 === 0 ? -42 : -47}
            transform={`rotate(${deg})`}
            className={deg <= shown && total > 0 ? 'stroke-brass' : 'stroke-rule'}
            style={{ transition: 'stroke 300ms', transitionDelay: `${(deg / 360) * 700}ms` }}
            strokeWidth={deg % 90 === 0 ? 2 : 1}
          />
        ))}
        <text y="-30" textAnchor="middle" className="fill-muted font-display text-2xs font-semibold">
          N
        </text>
        <g
          style={{ transform: `rotate(${shown}deg)`, transition: 'transform 1100ms cubic-bezier(.2,1.4,.4,1)' }}
        >
          <polygon points="0,-38 6,0 0,-4 -6,0" className={complete ? 'fill-sea' : 'fill-signal'} />
          <polygon points="0,38 6,0 0,4 -6,0" className="fill-muted/60" />
        </g>
        <circle r="4" className="fill-brass" />
      </svg>
      <figcaption className="font-mono text-xs leading-tight text-muted">
        <span className="block text-2xl font-medium text-ink">
          {done}
          <span className="text-muted">/{total}</span>
        </span>
        {complete ? t('dial.allDone') : t('dial.done')}
      </figcaption>
    </figure>
  )
}
