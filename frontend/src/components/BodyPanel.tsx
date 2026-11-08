import { useState } from 'react'
import { toast } from 'sonner'

import { useBodyTrend, useLogBody } from '../api/nutrition'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { decimal, parseDate } from '../lib/format'
import { button } from '../lib/ui'
import { LineChart } from './charts'
import { DataTable, Stat } from './DataBlocks'
import { SectionLabel } from './Layout'

/** Morning weight and weekly waist: entry, 7-day mean, weekly trend against the target loss. */
export function BodyPanel() {
  const { t, locale } = useI18n()
  const trend = useBodyTrend(8)
  const log = useLogBody()
  const [weight, setWeight] = useState('')
  const [waist, setWaist] = useState('')
  const d = trend.data
  const signed = (v: number, unit: string) => `${v > 0 ? '+' : ''}${decimal(v, locale)} ${unit}`
  const short = (day: string) => parseDate(day).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })

  const save = (metric: 'weight' | 'waist', raw: string, clear: () => void) => {
    const value = Number(raw.replace(',', '.'))
    if (!raw.trim() || !Number.isFinite(value)) return
    log.mutate({ metric, value }, { onSuccess: () => (clear(), toast(t('body.saved'))), onError: (error) => toast.error(error.message) })
  }

  const means = (d?.days ?? []).filter((x) => x.mean7 !== null).map((x) => ({ key: x.date, date: x.date, value: x.mean7 as number }))
  const tone = d?.status === 'on_target' ? 'text-chart' : d?.status ? 'text-brass' : 'text-muted'

  return (
    <section>
      <SectionLabel>{t('body.title')}</SectionLabel>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          save('weight', weight, () => setWeight(''))
          save('waist', waist, () => setWaist(''))
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">{t('body.weightToday')}</span>
          <input value={weight} onChange={(e) => setWeight(e.target.value)} inputMode="decimal" placeholder="kg" className="w-28 rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono focus:border-brass focus:outline-none" />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">{t('body.waist')}</span>
          <input value={waist} onChange={(e) => setWaist(e.target.value)} inputMode="decimal" placeholder="cm" className="w-28 rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono focus:border-brass focus:outline-none" />
        </label>
        <button type="submit" disabled={log.isPending || (!weight.trim() && !waist.trim())} className={button('primary')}>
          {t('body.save')}
        </button>
      </form>
      <p className="mt-1 font-mono text-2xs text-muted">{t('body.hint')}</p>

      {d && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label={t('body.mean7')} value={d.mean7 !== null ? `${decimal(d.mean7, locale)} kg` : '–'} note={t('body.weighIns', { n: d.days.slice(-7).filter((x) => x.kg !== null).length })} />
            <Stat
              label={t('body.week')}
              value={d.change_kg !== null ? signed(d.change_kg, 'kg') : '–'}
              note={d.change_pct !== null ? signed(d.change_pct, '%') : undefined}
            />
            <Stat label={t('body.target')} value={`${decimal(d.loss_min, locale)}–${decimal(d.loss_max, locale)} kg`} note={d.status ? undefined : t('body.noTrend')} />
            <Stat label={t('body.waist')} value={d.waist.length ? `${decimal(d.waist[d.waist.length - 1].cm, locale)} cm` : '–'} note={d.waist_change !== null ? signed(d.waist_change, 'cm') : undefined} />
          </div>
          {d.status && <p className={`mt-2 text-sm ${tone}`}>{t(`body.status.${d.status}` as MessageKey, { rate: decimal(Math.abs(d.loss_per_week ?? 0), locale) })}</p>}
          {means.length > 1 && (
            <div className="mt-4">
              <p className="mb-1 text-sm text-muted">{t('body.meanChart')}</p>
              <LineChart
                data={means}
                dayLabel={short}
                format={(v) => `${decimal(v, locale)} kg`}
                ariaLabel={t('body.meanChart')}
                tooltip={(p) => {
                  const day = d.days.find((x) => x.date === p.date)
                  return (
                    <>
                      <strong className="font-semibold">{decimal(p.value, locale)} kg</strong>
                      <span className="ml-2 text-muted">
                        {short(p.date)}
                        {day?.kg != null && ` · ${t('body.weighIn', { kg: decimal(day.kg, locale) })}`}
                      </span>
                    </>
                  )
                }}
              />
              <DataTable
                head={[t('body.weekOf'), t('body.weekValues')]}
                rows={[...d.weeks].reverse().map((w) => [short(w.week_start), [w.kg !== null ? `${decimal(w.kg, locale)} kg` : '–', w.waist_cm !== null ? `${decimal(w.waist_cm, locale)} cm` : null].filter(Boolean).join(' · ')])}
              />
            </div>
          )}
        </>
      )}
    </section>
  )
}
