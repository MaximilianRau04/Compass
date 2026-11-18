import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router'

import type { DayHeartRate, HealthSummary, NutritionSummary, TrainingSummary } from '../api/types'
import { useI18n } from '../i18n/context'
import { addDays, clockTime, localDay, parseDate, rangeDays, relativeDay } from '../lib/format'
import { MiniBars, Sparkline } from './charts'
import { CountUp } from './CountUp'

/* The body at a glance on the today page: one tile per measure, each with its trend and a link
 * to the page with the full charts. */

function Tile({
  to,
  label,
  value,
  unit,
  note,
  warn,
  accent,
  order,
  children,
}: {
  to: string
  label: string
  value: ReactNode
  unit?: string
  note?: string
  warn?: string
  /** The measure's colour token, e.g. var(--m-sleep): the dot, the hover edge and the marks. */
  accent: string
  /** Position in the grid, staggers the entrance. */
  order: number
  children?: ReactNode
}) {
  return (
    <Link
      to={to}
      style={{ '--accent': accent, '--i': order } as CSSProperties}
      className="rise group flex min-h-[8.75rem] flex-col rounded-lg border border-rule bg-paper-raised px-3.5 py-3 transition-colors hover:border-(--accent)"
    >
      <span className="flex items-center justify-between text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-(--accent)" />
          {label}
        </span>
        <span aria-hidden className="text-brass opacity-0 transition-opacity group-hover:opacity-100">
          →
        </span>
      </span>
      <span className="mt-1 flex items-baseline gap-1.5">
        <span className="text-3xl leading-none font-semibold tabular-nums">{value}</span>
        {unit && <span className="text-sm text-muted">{unit}</span>}
      </span>
      {note && <span className="mt-1 truncate font-mono text-2xs text-muted">{note}</span>}
      {warn && <span className="mt-0.5 font-mono text-2xs text-brass">{warn}</span>}
      <span className="mt-auto block pt-2">{children}</span>
    </Link>
  )
}

const weekday = (day: string, locale: string) => parseDate(day).toLocaleDateString(locale, { weekday: 'short' })

export function BodyTiles({
  today,
  health,
  heart,
  food,
  training,
}: {
  today: string
  health: HealthSummary | undefined
  heart: DayHeartRate | undefined
  food: NutritionSummary | undefined
  training: TrainingSummary | undefined
}) {
  const { t, locale } = useI18n()
  const week = rangeDays(addDays(today, -6), today)
  const metrics = new Map(health?.days.map((d) => [d.date, d]) ?? [])
  const tiles: ReactNode[] = []

  const night = health?.last_night
  if (night && night.local_date >= addDays(today, -1)) {
    const synced = health.sync?.last_success_at
    tiles.push(
      <Tile
        key="sleep"
        to="/sleep"
        label={t('tile.sleep')}
        accent="var(--m-sleep)"
        order={tiles.length}
        value={<CountUp value={night.asleep_minutes} format={(n) => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`} />}
        unit="h"
        note={`${clockTime(night.start_at, locale)}–${clockTime(night.end_at, locale)}`}
        warn={night.local_date < today ? t('tile.sleepOld', { when: synced ? clockTime(synced, locale) : '–' }) : undefined}
      >
        <MiniBars
          values={week.map((d) => metrics.get(d)?.sleep_minutes ?? null)}
          titles={week.map((d) => `${weekday(d, locale)}: ${metrics.get(d)?.sleep_minutes ? `${Math.round((metrics.get(d)!.sleep_minutes! / 60) * 10) / 10} h` : '–'}`)}
          ariaLabel={t('tile.sleepTrend')}
          color="var(--m-sleep)"
        />
      </Tile>,
    )
  }

  if (heart && (heart.points.length > 0 || heart.resting !== null)) {
    const parts = [
      heart.min !== null && heart.max !== null ? t('tile.hrRange', { min: heart.min, max: heart.max }) : null,
      heart.last ? t('tile.hrLast', { bpm: heart.last.bpm, time: clockTime(heart.last.time, locale) }) : null,
    ].filter(Boolean)
    tiles.push(
      <Tile
        key="hr"
        to="/sleep#heart-rate"
        label={t('tile.hr')}
        accent="var(--m-heart)"
        order={tiles.length}
        value={heart.resting !== null ? <CountUp value={heart.resting} format={String} /> : '–'}
        unit={t('tile.hrUnit')}
        note={parts.join(' · ')}
      >
        <Sparkline values={heart.points.map((p) => p.bpm)} ariaLabel={t('tile.hrTrend')} color="var(--m-heart)" />
      </Tile>,
    )
  }

  const steps = metrics.get(today)?.steps
  if (health && health.days.length > 0) {
    const known = week.map((d) => metrics.get(d)?.steps).filter((v): v is number => typeof v === 'number')
    const avg = known.length ? Math.round(known.reduce((a, b) => a + b, 0) / known.length) : null
    tiles.push(
      <Tile
        key="steps"
        to="/sleep"
        label={t('tile.steps')}
        accent="var(--m-steps)"
        order={tiles.length}
        value={steps != null ? <CountUp value={steps} format={(n) => n.toLocaleString(locale)} /> : '–'}
        note={avg !== null ? t('tile.avg7', { value: avg.toLocaleString(locale) }) : undefined}>
        <MiniBars
          values={week.map((d) => metrics.get(d)?.steps ?? null)}
          titles={week.map((d) => `${weekday(d, locale)}: ${metrics.get(d)?.steps?.toLocaleString(locale) ?? '–'}`)}
          ariaLabel={t('tile.stepsTrend')}
          color="var(--m-steps)"
        />
      </Tile>,
    )
  }

  if (food) {
    const day = food.days.find((d) => d.date === today)
    const goal = food.goals.kcal
    const share = day && goal ? Math.min(1, day.kcal / goal) : 0
    tiles.push(
      <Tile
        key="food"
        to="/nutrition"
        label={t('tile.food')}
        accent="var(--m-food)"
        order={tiles.length}
        value={day ? <CountUp value={Math.round(day.kcal)} format={(n) => n.toLocaleString(locale)} /> : '–'}
        unit={day ? 'kcal' : undefined}
        note={
          day
            ? [goal ? t('nutrition.ofGoal', { goal: Math.round(goal).toLocaleString(locale) }) : null, day.protein_g !== null ? t('today.protein', { g: `${Math.round(day.protein_g)} g` }) : null].filter(Boolean).join(' · ')
            : t('tile.foodNone')
        }
      >
        {goal ? (
          <span className="block h-2 overflow-hidden rounded-full bg-rule" role="img" aria-label={t('tile.foodShare', { n: Math.round(share * 100) })}>
            <span className="fill-in block h-full rounded-full bg-m-food" style={{ width: `${share * 100}%` }} />
          </span>
        ) : null}
      </Tile>,
    )
  }

  if (training && training.sessions > 0) {
    const last = training.last_session
    const weeks = training.weeks.slice(-8)
    tiles.push(
      <Tile
        key="training"
        to="/training"
        label={t('tile.training')}
        accent="var(--m-training)"
        order={tiles.length}
        value={<CountUp value={training.this_week_sessions} format={String} />}
        unit={t('tile.thisWeek')}
        note={last ? `${last.workout_name} · ${relativeDay(localDay(last.started_at), today, t, locale)}` : undefined}
      >
        <MiniBars values={weeks.map((w) => w.sessions)} titles={weeks.map((w) => t('tile.weekSessions', { week: w.week_start, n: w.sessions }))} ariaLabel={t('tile.trainingTrend')} color="var(--m-training)" />
      </Tile>,
    )
  }

  if (tiles.length === 0) return null
  // An odd last tile spans both columns instead of leaving a hole.
  return <div className="grid grid-cols-2 gap-2 [&>:last-child:nth-child(odd)]:col-span-2">{tiles}</div>
}
