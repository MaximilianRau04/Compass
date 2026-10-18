import { useState } from 'react'

import { useHealthSummary } from '../api/sleep'
import { useTodayDate } from '../api/tasks'
import type { HealthSummary, SleepNight, SleepNightDetail } from '../api/types'
import { ColumnChart, Hypnogram, LineChart } from '../components/charts'
import { DataTable, Stat } from '../components/DataBlocks'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { clockTime, compact, localDay, parseDate, pill, rangeDays, relativeDay } from '../lib/format'
import { appName, hours, LANES, type Lane, laneOf } from '../lib/health'

const RANGES = [7, 30, 90]
const STAGES: Lane[] = ['deep', 'light', 'rem', 'awake']

function LastNight({ night, today }: { night: SleepNightDetail; today: string }) {
  const { t, locale } = useI18n()
  const bpm = night.heart_rate.map((p) => p.bpm)
  const segments = night.stages.map((s) => ({ start: s.start, end: s.end, lane: LANES.indexOf(laneOf(s.stage)) }))
  return (
    <section className="mb-8 rounded-md border border-rule bg-paper-raised px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-xs text-muted">
          {t('sleep.lastNight')} · {relativeDay(night.local_date, today, t, locale)}
        </p>
        <p className="font-mono text-[11px] text-muted">{appName(night.source_app)}</p>
      </div>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
        <span className="text-4xl font-semibold">{hours(night.asleep_minutes)}</span>
        <span className="text-muted">{t('sleep.asleep')}</span>
      </p>
      <p className="mt-0.5 font-mono text-[12px] text-muted">
        {clockTime(night.start_at, locale)}–{clockTime(night.end_at, locale)} · {t('sleep.inBed', { time: hours(night.in_bed_minutes) })}
        {bpm.length > 0 &&
          ` · ${t('sleep.nightHr', { min: Math.min(...bpm), max: Math.max(...bpm), avg: Math.round(bpm.reduce((a, b) => a + b, 0) / bpm.length) })}`}
      </p>
      {segments.length > 0 && (
        <div className="mt-3">
          <Hypnogram
            segments={segments}
            start={night.start_at}
            end={night.end_at}
            lanes={LANES.map((lane) => t(`sleep.stage.${lane}` as MessageKey))}
            awakeLane={LANES.indexOf('awake')}
            hourLabel={(d) => String(d.getHours())}
            ariaLabel={t('sleep.hypnogram')}
            tooltip={(s) => {
              const minutes = Math.round((new Date(s.end).getTime() - new Date(s.start).getTime()) / 60_000)
              return (
                <>
                  <strong className="font-semibold">{t(`sleep.stage.${LANES[s.lane]}` as MessageKey)}</strong>
                  <span className="ml-2 text-muted">
                    {clockTime(s.start, locale)}–{clockTime(s.end, locale)} · {t('training.duration', { n: minutes })}
                  </span>
                </>
              )
            }}
          />
        </div>
      )}
    </section>
  )
}

function StageAverages({ averages }: { averages: HealthSummary['averages'] }) {
  const { t } = useI18n()
  const values = STAGES.map((stage) => [stage, averages[`${stage}_minutes`]] as const)
  if (values.every(([, v]) => v === null)) return null
  const max = Math.max(...values.map(([, v]) => v ?? 0), 1)
  const total = values.reduce((sum, [, v]) => sum + (v ?? 0), 0) || 1
  return (
    <section>
      <SectionLabel>{t('sleep.stagesAvg')}</SectionLabel>
      <ul className="mt-3 space-y-2">
        {values.map(([stage, v]) => (
          <li key={stage} className="grid grid-cols-[5.5rem_1fr_6.5rem] items-center gap-3 text-sm">
            <span>{t(`sleep.stage.${stage}` as MessageKey)}</span>
            <span className="h-3">
              {v !== null && v > 0 && (
                <span
                  className={`block h-3 rounded-r-[4px] ${stage === 'awake' ? 'bg-muted' : 'bg-chart'}`}
                  style={{ width: `${(v / max) * 100}%` }}
                />
              )}
            </span>
            <span className="text-right font-mono text-[12px] tabular-nums">
              {v === null ? '–' : `${hours(v)} · ${Math.round((v / total) * 100)} %`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function SyncLine({ sync, today }: { sync: HealthSummary['sync']; today: string }) {
  const { t, locale } = useI18n()
  if (!sync?.last_success_at) return <p className="mb-6 font-mono text-[11px] text-muted">{t('sleep.never')}</p>
  const when = `${relativeDay(localDay(sync.last_success_at), today, t, locale)} ${clockTime(sync.last_success_at, locale)}`
  return (
    <p className="mb-6 font-mono text-[11px] text-muted">
      {t('sleep.synced', { when })}
      {sync.device && ` · ${sync.device}`}
      {sync.last_error && <span className="block text-signal">{t('sleep.syncError', { message: sync.last_error })}</span>}
    </p>
  )
}

export function SleepPage() {
  const { t, locale } = useI18n()
  const [range, setRange] = useState(30)
  const summary = useHealthSummary(range)
  const today = useTodayDate()

  const header = (
    <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('sleep.title')}</h1>
      <div role="group" aria-label={t('sleep.range')} className="flex gap-1.5">
        {RANGES.map((n) => (
          <button key={n} type="button" className={pill(range === n)} aria-pressed={range === n} onClick={() => setRange(n)}>
            {t('sleep.daysN', { n })}
          </button>
        ))}
      </div>
    </header>
  )

  if (summary.error) return <>{header}<p className="text-signal">{t('sleep.loadError', { message: summary.error.message })}</p></>
  if (summary.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const data = summary.data
  if (!data.last_night && data.days.length === 0) {
    return (
      <>
        {header}
        <SyncLine sync={data.sync} today={today} />
        <p className="max-w-md text-muted">{t('sleep.empty')}</p>
      </>
    )
  }

  const days = rangeDays(data.since, data.until)
  const dayLabel = (d: string) => parseDate(d).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })
  const longLabel = (d: string) => parseDate(d).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })
  const nights = new Map<string, SleepNight>(data.nights.map((n) => [n.local_date, n]))
  const metrics = new Map(data.days.map((m) => [m.date, m]))

  const sleepBars = days.map((d) => ({ key: d, value: (nights.get(d)?.asleep_minutes ?? 0) / 60, label: dayLabel(d) }))
  const stepBars = days.map((d) => ({ key: d, value: metrics.get(d)?.steps ?? 0, label: dayLabel(d) }))
  const resting = data.days
    .filter((m) => m.resting_hr !== null)
    .map((m) => ({ key: m.date, date: m.date, value: m.resting_hr as number }))
  const avg = data.averages

  return (
    <>
      {header}
      <SyncLine sync={data.sync} today={today} />

      {data.last_night && <LastNight night={data.last_night} today={today} />}

      <div className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label={t('sleep.avgSleep')} value={avg.sleep_minutes === null ? '–' : hours(avg.sleep_minutes)} note={t('sleep.daysN', { n: range })} />
        <Stat label={t('sleep.restingHr')} value={avg.resting_hr === null ? '–' : `${avg.resting_hr} bpm`} />
        <Stat label={t('sleep.stepsAvg')} value={avg.steps === null ? '–' : compact(avg.steps, locale)} />
      </div>

      <div className="space-y-10">
        <section>
          <SectionLabel>{t('sleep.perNight')}</SectionLabel>
          <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('sleep.perNightHint')}</p>
          <ColumnChart
            data={sleepBars}
            format={(v) => hours(v * 60)}
            ariaLabel={t('sleep.perNight')}
            tooltip={(d) => {
              const n = nights.get(d.key)
              if (!n) return <span className="text-muted">{longLabel(d.key)} · {t('sleep.noData')}</span>
              return (
                <>
                  <strong className="font-semibold">{hours(n.asleep_minutes)}</strong>
                  <span className="ml-2 text-muted">
                    {longLabel(d.key)} · {clockTime(n.start_at, locale)}–{clockTime(n.end_at, locale)}
                    {n.deep_minutes !== null && ` · ${t('sleep.stage.deep')} ${hours(n.deep_minutes)}`}
                    {n.rem_minutes !== null && ` · ${t('sleep.stage.rem')} ${hours(n.rem_minutes)}`}
                  </span>
                </>
              )
            }}
          />
          <DataTable
            head={[t('sleep.night'), t('sleep.value')]}
            rows={[...data.nights].reverse().map((n) => [longLabel(n.local_date), hours(n.asleep_minutes)])}
          />
        </section>

        <StageAverages averages={avg} />

        {resting.length > 0 && (
          <section>
            <SectionLabel>{t('sleep.restingTrend')}</SectionLabel>
            <div className="mt-3">
              <LineChart
                data={resting}
                format={(v) => `${v} bpm`}
                ariaLabel={t('sleep.restingTrend')}
                dayLabel={range <= 31 ? dayLabel : undefined}
                tooltip={(p) => (
                  <>
                    <strong className="font-semibold">{p.value} bpm</strong>
                    <span className="ml-2 text-muted">{longLabel(p.date)}</span>
                  </>
                )}
              />
            </div>
            <DataTable head={[t('training.date'), t('sleep.value')]} rows={[...resting].reverse().map((p) => [longLabel(p.date), `${p.value} bpm`])} />
          </section>
        )}

        {stepBars.some((d) => d.value > 0) && (
          <section>
            <SectionLabel>{t('sleep.stepsPerDay')}</SectionLabel>
            <div className="mt-3">
              <ColumnChart
                data={stepBars}
                format={(v) => compact(v, locale)}
                ariaLabel={t('sleep.stepsPerDay')}
                tooltip={(d) => (
                  <>
                    <strong className="font-semibold">{d.value ? d.value.toLocaleString(locale) : '–'}</strong>
                    <span className="ml-2 text-muted">{longLabel(d.key)}</span>
                  </>
                )}
              />
            </div>
            <DataTable
              head={[t('training.date'), t('sleep.value')]}
              rows={[...data.days].reverse().filter((m) => m.steps !== null).map((m) => [longLabel(m.date), (m.steps as number).toLocaleString(locale)])}
            />
          </section>
        )}

        {data.workouts.length > 0 && (
          <section>
            <SectionLabel count={data.workouts.length}>{t('sleep.workouts')}</SectionLabel>
            <p className="mt-1 font-mono text-[11px] text-muted">{t('sleep.workoutsHint')}</p>
            <ul className="divide-y divide-rule/60">
              {data.workouts.map((w) => (
                <li key={w.id} className="flex items-baseline justify-between gap-3 py-2.5">
                  <span>
                    <span className="font-medium">{w.title ?? w.exercise?.replaceAll('_', ' ') ?? appName(w.source_app)}</span>
                    <span className="ml-2 font-mono text-[11px] text-muted">{relativeDay(localDay(w.start_at), today, t, locale)}</span>
                  </span>
                  <span className="font-mono text-[11px] text-muted">
                    {appName(w.source_app)} · {t('training.duration', { n: w.duration_minutes })}
                    {w.gymday_duplicate && ` · ${t('sleep.duplicate')}`}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  )
}
