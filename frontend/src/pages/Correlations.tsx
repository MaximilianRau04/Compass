import { useState } from 'react'
import { Link } from 'react-router'

import { type Correlation, useCorrelation, useCorrelations } from '../api/correlations'
import { ScatterChart } from '../components/charts'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { parseDate, pill } from '../lib/format'
import { pageTitle } from '../lib/ui'

const RANGES = [30, 90, 180, 365]

const metric = (name: string) => `corr.metric.${name}` as MessageKey

function strength(r: number | null): MessageKey {
  if (r === null) return 'corr.tooFew'
  const a = Math.abs(r)
  if (a < 0.1) return 'corr.none'
  if (a < 0.3) return r > 0 ? 'corr.weakPos' : 'corr.weakNeg'
  if (a < 0.5) return r > 0 ? 'corr.midPos' : 'corr.midNeg'
  return r > 0 ? 'corr.strongPos' : 'corr.strongNeg'
}

function PairLabel({ c }: { c: Pick<Correlation, 'x' | 'y' | 'lag'> }) {
  const { t } = useI18n()
  return (
    <>
      {t(metric(c.x))} → {t(metric(c.y))}
      {c.lag > 0 && <span className="font-mono text-2xs text-muted"> {t('corr.nextDay', { n: c.lag })}</span>}
    </>
  )
}

function Detail({ pair, days }: { pair: Correlation; days: number }) {
  const { t, locale } = useI18n()
  const result = useCorrelation(pair.x, pair.y, pair.lag, days)
  if (result.isPending) return <p className="text-sm text-muted" role="status">{t('common.loading')}</p>
  if (result.isError) return <p className="text-sm text-signal" role="alert">{t('corr.loadError')}</p>
  const data = result.data
  const points = data.points.map((p) => ({
    key: p.date,
    x: p.x,
    y: p.y,
    label: parseDate(p.date).toLocaleDateString(locale, { day: 'numeric', month: 'short' }),
  }))
  return (
    <section>
      <SectionLabel>{`${t(metric(data.x))} → ${t(metric(data.y))}${data.lag > 0 ? ` (${t('corr.nextDay', { n: data.lag })})` : ''}`}</SectionLabel>
      <p className="mt-1 text-sm text-muted">
        {t(strength(data.r))} · {t('corr.days', { n: data.n })}
        {data.r !== null && <span className="font-mono"> · r = {data.r.toLocaleString(locale)}</span>}
      </p>
      {data.n < 10 && <p className="mt-2 text-sm text-muted">{t('corr.fewDays')}</p>}
      <ScatterChart points={points} xLabel={t(metric(data.x))} yLabel={t(metric(data.y))} format={(v) => v.toLocaleString(locale, { maximumFractionDigits: 1 })} />
    </section>
  )
}

/** Pairs of daily values (sleep, training, food, journal …) and how closely they go together. */
export function CorrelationsPage() {
  const { t, locale } = useI18n()
  const [days, setDays] = useState(90)
  const list = useCorrelations(days)
  const [chosen, setChosen] = useState<Correlation | null>(null)
  const pair = list.data?.find((c) => chosen && c.x === chosen.x && c.y === chosen.y && c.lag === chosen.lag)
    ?? list.data?.find((c) => c.r !== null) ?? list.data?.[0] ?? null
  const same = (a: Correlation, b: Correlation | null) => !!b && a.x === b.x && a.y === b.y && a.lag === b.lag

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h1 className={pageTitle}>{t('nav.correlations')}</h1>
        <div className="flex gap-1.5">
          {RANGES.map((n) => (
            <button key={n} type="button" className={pill(days === n)} aria-pressed={days === n} onClick={() => setDays(n)}>
              {t('corr.range', { n })}
            </button>
          ))}
        </div>
      </header>
      <p className="mb-6 max-w-2xl text-sm leading-relaxed text-muted">{t('corr.intro')} <Link to="/journal" className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">{t('corr.journalLink')} →</Link></p>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <ul className="divide-y divide-rule/60">
          {list.isPending && <li className="py-2 font-mono text-sm text-muted" role="status">{t('common.loading')}</li>}
          {list.isError && <li className="py-2 text-sm text-signal" role="alert">{t('corr.loadError')}</li>}
          {list.data?.length === 0 && <li className="py-2 text-sm text-muted">{t('corr.empty')}</li>}
          {list.data?.map((c) => (
            <li key={`${c.x}-${c.y}-${c.lag}`}>
              <button type="button" onClick={() => setChosen(c)} aria-pressed={same(c, pair)} className={`flex w-full items-baseline justify-between gap-3 py-2 text-left hover:text-brass ${same(c, pair) ? 'text-brass' : ''}`}>
                <span>
                  <PairLabel c={c} />
                </span>
                <span className="font-mono text-2xs whitespace-nowrap text-muted">{c.r !== null ? `r ${c.r.toLocaleString(locale)}` : t('corr.daysShort', { n: c.n })}</span>
              </button>
            </li>
          ))}
        </ul>
        {pair && <Detail pair={pair} days={days} />}
      </div>
    </>
  )
}
