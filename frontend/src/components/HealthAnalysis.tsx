import { useHealthAnalysis } from '../api/sleep'
import { useI18n } from '../i18n/context'
import { decimal, parseDate } from '../lib/format'
import { hours } from '../lib/health'
import { ColumnChart, LineChart } from './charts'
import { DataTable, Stat } from './DataBlocks'
import { SectionLabel } from './Layout'

/** Sleep rhythm, the resting heart rate trend and zone 2 minutes per week. */
export function HealthAnalysis({ days }: { days: number }) {
  const { t, locale } = useI18n()
  const analysis = useHealthAnalysis(Math.max(days, 14))
  const a = analysis.data
  if (!a) return null
  const c = a.consistency
  const short = (d: string) => parseDate(d).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })
  const long = (d: string) => parseDate(d).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })
  const resting = a.resting.days.filter((d) => d.mean7 !== null).map((d) => ({ key: d.date, date: d.date, value: d.mean7 as number }))
  const zone = a.zone2_weeks.map((w) => ({ key: w.week_start, value: w.minutes, label: short(w.week_start) }))

  return (
    <>
      {c.nights > 0 && (
        <section>
          <SectionLabel>{t('rhythm.title')}</SectionLabel>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label={t('rhythm.bed')} value={c.median_bedtime ?? '–'} note={c.bedtime_sd_minutes !== null ? t('rhythm.sd', { n: c.bedtime_sd_minutes }) : undefined} />
            <Stat label={t('rhythm.wake')} value={c.median_wake_time ?? '–'} note={c.wake_time_sd_minutes !== null ? t('rhythm.sd', { n: c.wake_time_sd_minutes }) : undefined} />
            <Stat label={t('rhythm.short')} value={`${c.short_nights.length} / ${c.nights}`} note={t('rhythm.shortHint')} />
            <Stat
              label={t('rhythm.early')}
              value={String(c.early_nights.length)}
              note={c.avg_asleep_early !== null ? t('rhythm.earlyAvg', { early: hours(c.avg_asleep_early), other: c.avg_asleep_other !== null ? hours(c.avg_asleep_other) : '–' }) : t('rhythm.earlyHint')}
            />
          </div>
          {c.early_nights.length > 0 && (
            <DataTable head={[t('rhythm.earlyNight'), t('sleep.value')]} rows={c.early_nights.map((n) => [`${long(n.date)} · ${n.first_event} ${n.title}`, hours(n.asleep_minutes)])} />
          )}
        </section>
      )}

      {resting.length > 1 && (
        <section>
          <SectionLabel tone={a.resting.alert ? 'signal' : undefined}>{t('rhythm.resting')}</SectionLabel>
          {a.resting.alert ? (
            <p className="mt-2 rounded-md border border-signal/50 bg-signal/10 px-3 py-2 text-sm">
              {t('rhythm.restingAlert', { now: decimal(a.resting.latest_mean7 ?? 0, locale), median: decimal(a.resting.median ?? 0, locale) })}
            </p>
          ) : (
            <p className="mt-1 font-mono text-2xs text-muted">{t('rhythm.restingHint', { median: decimal(a.resting.median ?? 0, locale) })}</p>
          )}
          <div className="mt-3">
            <LineChart
              color="var(--m-heart)"
              data={resting}
              dayLabel={short}
              format={(v) => `${decimal(v, locale)} bpm`}
              ariaLabel={t('rhythm.resting')}
              tooltip={(p) => {
                const day = a.resting.days.find((d) => d.date === p.date)
                return (
                  <>
                    <strong className="font-semibold">{decimal(p.value, locale)} bpm</strong>
                    <span className="ml-2 text-muted">
                      {long(p.date)}
                      {day?.bpm != null && ` · ${t('rhythm.thatDay', { bpm: day.bpm })}`}
                    </span>
                  </>
                )
              }}
            />
          </div>
        </section>
      )}

      {zone.some((z) => z.value > 0) && (
        <section>
          <SectionLabel>{t('zone2.title')}</SectionLabel>
          <p className="mt-1 mb-2 font-mono text-2xs text-muted">{t('zone2.hint', { low: a.zone2_low, high: a.zone2_high, max: a.hr_max })}</p>
          <ColumnChart
            color="var(--m-heart)"
            data={zone}
            format={(v) => `${v} min`}
            ariaLabel={t('zone2.title')}
            tooltip={(d) => {
              const week = a.zone2_weeks.find((w) => w.week_start === d.key)!
              return (
                <>
                  <strong className="font-semibold">{week.minutes} min</strong>
                  <span className="ml-2 text-muted">
                    {t('training.weekOf', { date: d.label })} · {t('zone2.inTraining', { n: week.in_training })}
                  </span>
                </>
              )
            }}
          />
          <DataTable head={[t('training.date'), t('sleep.value')]} rows={[...a.zone2_weeks].reverse().map((w) => [t('training.weekOf', { date: short(w.week_start) }), `${w.minutes} min · ${t('zone2.inTraining', { n: w.in_training })}`])} />
        </section>
      )}
    </>
  )
}
