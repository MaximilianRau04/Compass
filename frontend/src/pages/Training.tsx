import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { useTodayDate } from '../api/tasks'
import {
  useExercises,
  useImportGymDay,
  useMergeExercise,
  useProgress,
  useSessionDetail,
  useSessions,
  useTrainingSummary,
} from '../api/training'
import type { Exercise, ProgressPoint, SessionBrief, Split } from '../api/types'
import { ColumnChart, LineChart } from '../components/charts'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { compact, decimal, localDay, parseDate, relativeDay } from '../lib/format'
import { importMessage } from '../lib/training'

const WEEKS = 12
const SPLITS: Split[] = ['push', 'pull', 'legs', 'other']
type Metric = 'best_e1rm' | 'top_weight' | 'max_reps' | 'volume_kg'

const pill = (active: boolean) =>
  [
    'rounded-full border px-3 py-1 text-sm transition-colors',
    active ? 'border-ink bg-ink text-paper' : 'border-rule text-muted hover:border-ink hover:text-ink',
  ].join(' ')

function ImportButton() {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const upload = useImportGymDay()
  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file) return
          upload.mutate(file, {
            onSuccess: (result) => toast(importMessage(result, t)),
            onError: (error) => toast.error(error.message),
          })
        }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={upload.isPending}
        className="rounded-md bg-brass px-3 py-2 text-sm font-medium text-brass-ink hover:opacity-90 disabled:opacity-50"
      >
        {upload.isPending ? t('training.importing') : t('training.import')}
      </button>
    </>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-md border border-rule bg-paper-raised px-3 py-2.5">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold">{value}</p>
      {note && <p className="truncate font-mono text-[11px] text-muted">{note}</p>}
    </div>
  )
}

function DataTable({ rows, head }: { rows: [string, string][]; head: [string, string] }) {
  const { t } = useI18n()
  return (
    <details className="mt-1 text-sm">
      <summary className="cursor-pointer font-mono text-[11px] text-muted hover:text-ink">{t('training.table')}</summary>
      <table className="mt-2 w-full font-mono text-[12px] tabular-nums">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1 font-normal">{head[0]}</th>
            <th className="py-1 text-right font-normal">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b]) => (
            <tr key={a} className="border-t border-rule/60">
              <td className="py-1">{a}</td>
              <td className="py-1 text-right">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

function shortDate(value: string, locale: string): string {
  return parseDate(value).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })
}

function Progression({ exercises }: { exercises: Exercise[] }) {
  const { t, locale } = useI18n()
  const [selected, setSelected] = useState<number | null>(null)
  const [metric, setMetric] = useState<Metric>('best_e1rm')
  const exercise = exercises.find((e) => e.id === selected) ?? exercises[0]
  const progress = useProgress(exercise?.id ?? null)
  if (!exercise) return null

  const metrics: Metric[] = exercise.bodyweight ? ['max_reps'] : ['best_e1rm', 'top_weight', 'max_reps', 'volume_kg']
  const active = metrics.includes(metric) ? metric : metrics[0]
  const unit = active === 'max_reps' ? '' : ' kg'
  const format = (v: number) => `${active === 'volume_kg' ? compact(v, locale) : decimal(v, locale)}${unit}`
  const points = (progress.data ?? [])
    .filter((p) => p[active] !== null)
    .map((p: ProgressPoint) => ({ key: String(p.session_id), date: p.date, value: p[active] as number, point: p }))

  return (
    <section>
      <SectionLabel>{t('training.progress')}</SectionLabel>
      <div className="my-3 flex flex-wrap items-center gap-2">
        <select
          aria-label={t('training.exercise')}
          value={exercise.id}
          onChange={(e) => setSelected(Number(e.target.value))}
          className="max-w-full rounded-md border border-rule bg-paper-raised px-2 py-1.5 text-sm focus:border-brass focus:outline-none"
        >
          {exercises.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} ({e.sessions})
            </option>
          ))}
        </select>
        <div className="flex flex-wrap gap-1.5">
          {metrics.map((m) => (
            <button key={m} type="button" className={pill(active === m)} onClick={() => setMetric(m)}>
              {t(`metric.${m}` as MessageKey)}
            </button>
          ))}
        </div>
      </div>
      {progress.isSuccess && points.length === 0 && <p className="text-muted">{t('training.noProgress')}</p>}
      <LineChart
        data={points}
        format={format}
        ariaLabel={`${exercise.name}: ${t(`metric.${active}` as MessageKey)}`}
        tooltip={(p) => {
          const point = points.find((x) => x.key === p.key)?.point
          return (
            <>
              <strong className="font-semibold">{format(p.value)}</strong>
              <span className="ml-2 text-muted">
                {parseDate(p.date).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: '2-digit' })}
                {point && ` · ${point.workout_name} · ${t('training.setsN', { n: point.sets })}`}
              </span>
            </>
          )
        }}
      />
      <DataTable
        head={[t('training.date'), t(`metric.${active}` as MessageKey)]}
        rows={[...points].reverse().map((p) => [p.date, format(p.value)])}
      />
    </section>
  )
}

function SessionRow({ session, today }: { session: SessionBrief; today: string }) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(false)
  const detail = useSessionDetail(open ? session.id : null)
  return (
    <li className="py-2.5">
      <details onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
          <span>
            <span className="font-medium">{session.workout_name}</span>
            <span className="ml-2 font-mono text-[11px] text-muted">{relativeDay(localDay(session.started_at), today, t, locale)}</span>
          </span>
          <span className="font-mono text-[11px] text-muted">
            {session.duration_minutes !== null && `${t('training.duration', { n: session.duration_minutes })} · `}
            {t('training.exercisesN', { n: session.exercises })} · {t('training.setsN', { n: session.sets })} ·{' '}
            {compact(session.volume_kg, locale)} kg
          </span>
        </summary>
        {detail.data && (
          <ul className="mt-2 space-y-1 border-l-2 border-chart/60 pl-3 text-sm">
            {detail.data.exercise_sets.map((group) => (
              <li key={group.exercise_id} className="flex flex-wrap justify-between gap-x-3">
                <span>{group.name}</span>
                <span className="font-mono text-[12px] text-muted tabular-nums">
                  {group.sets
                    .map((s) => (s.weight_kg === null ? `${t('training.bodyweight')} × ${s.reps}` : `${decimal(s.weight_kg, locale)} × ${s.reps}`))
                    .join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </li>
  )
}

function MergeExercises({ exercises }: { exercises: Exercise[] }) {
  const { t } = useI18n()
  const merge = useMergeExercise()
  const [targets, setTargets] = useState<Record<number, number>>({})
  return (
    <details>
      <summary className="cursor-pointer list-none">
        <SectionLabel count={exercises.length}>{t('training.manage')}</SectionLabel>
      </summary>
      <p className="my-3 max-w-xl text-sm text-muted">{t('training.manageHint')}</p>
      <ul className="divide-y divide-rule/60">
        {exercises.map((exercise) => {
          const target = targets[exercise.id]
          return (
            <li key={exercise.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="min-w-0">
                <span className="block">{exercise.name}</span>
                <span className="font-mono text-[11px] text-muted">
                  {t('training.sessionsN', { n: exercise.sessions })}
                  {exercise.aliases.filter((a) => a !== exercise.name).length > 0 &&
                    ` · ${t('training.aliases', { names: exercise.aliases.filter((a) => a !== exercise.name).join(', ') })}`}
                </span>
              </span>
              <span className="flex gap-1.5">
                <select
                  aria-label={`${exercise.name}: ${t('training.mergeInto')}`}
                  value={target ?? ''}
                  onChange={(e) => setTargets({ ...targets, [exercise.id]: Number(e.target.value) })}
                  className="max-w-48 rounded-md border border-rule bg-paper-raised px-2 py-1 text-sm"
                >
                  <option value="">{t('training.mergeInto')}</option>
                  {exercises
                    .filter((e) => e.id !== exercise.id)
                    .map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.name}
                      </option>
                    ))}
                </select>
                {target && (
                  <button
                    type="button"
                    disabled={merge.isPending}
                    onClick={() =>
                      merge.mutate(
                        { id: exercise.id, into: target },
                        {
                          onSuccess: (result) => toast(t('training.merged', { from: exercise.name, to: result.name })),
                          onError: (error) => toast.error(error.message),
                        },
                      )
                    }
                    className="rounded-md border border-brass px-2 py-1 text-sm text-brass hover:bg-brass/10"
                  >
                    {t('training.merge')}
                  </button>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </details>
  )
}

export function TrainingPage() {
  const { t, locale } = useI18n()
  const summary = useTrainingSummary(WEEKS)
  const sessions = useSessions()
  const exercises = useExercises()
  const today = useTodayDate()

  const header = (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('training.title')}</h1>
      <ImportButton />
    </header>
  )

  if (summary.error) return <>{header}<p className="text-signal">{t('training.loadError', { message: summary.error.message })}</p></>
  if (summary.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const data = summary.data
  if (!data.last_session) {
    return (
      <>
        {header}
        <p className="max-w-md text-muted">{t('training.empty')}</p>
        <p className="mt-3 max-w-md text-sm text-muted">{t('training.importHint')}</p>
      </>
    )
  }

  const weeks = data.weeks.map((w) => ({ key: w.week_start, value: w.volume_kg, label: shortDate(w.week_start, locale), week: w }))
  const splitMax = Math.max(...SPLITS.map((s) => data.split[s] ?? 0), 1)
  const last = data.last_session

  return (
    <>
      {header}
      <div className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label={t('training.thisWeek')} value={String(data.this_week_sessions)} />
        <Stat label={t('training.inWeeks', { n: WEEKS })} value={String(data.sessions)} note={`${compact(data.volume_kg, locale)} kg`} />
        <Stat
          label={t('training.lastSession')}
          value={relativeDay(localDay(last.started_at), today, t, locale)}
          note={`${last.workout_name} · ${t('training.setsN', { n: last.sets })}`}
        />
      </div>

      <div className="space-y-10">
        <section>
          <SectionLabel>{t('training.weeklyVolume')}</SectionLabel>
          <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('training.weeklyVolumeHint')}</p>
          <ColumnChart
            data={weeks}
            format={(v) => compact(v, locale)}
            ariaLabel={t('training.weeklyVolume')}
            tooltip={(d) => {
              const week = weeks.find((w) => w.key === d.key)!.week
              return (
                <>
                  <strong className="font-semibold">{decimal(d.value, locale)} kg</strong>
                  <span className="ml-2 text-muted">
                    {t('training.weekOf', { date: d.label })} · {t('training.sessionsN', { n: week.sessions })}
                  </span>
                </>
              )
            }}
          />
          <DataTable
            head={[t('training.date'), t('training.value')]}
            rows={[...weeks].reverse().map((w) => [t('training.weekOf', { date: w.label }), `${decimal(w.value, locale)} kg`])}
          />
        </section>

        <section>
          <SectionLabel>{t('training.split', { n: WEEKS })}</SectionLabel>
          <ul className="mt-3 space-y-2">
            {SPLITS.map((split) => {
              const n = data.split[split] ?? 0
              return (
                <li key={split} className="grid grid-cols-[5.5rem_1fr_2rem] items-center gap-3 text-sm">
                  <span>{t(`split.${split}`)}</span>
                  <span className="h-3">
                    {n > 0 && <span className="block h-3 rounded-r-[4px] bg-chart" style={{ width: `${(n / splitMax) * 100}%` }} />}
                  </span>
                  <span className="text-right font-mono text-[12px] tabular-nums">{n}</span>
                </li>
              )
            })}
          </ul>
        </section>

        {exercises.data && <Progression exercises={exercises.data} />}

        <section>
          <SectionLabel>{t('training.recent')}</SectionLabel>
          <ul className="divide-y divide-rule/60">
            {sessions.data?.map((s) => <SessionRow key={s.id} session={s} today={today} />)}
          </ul>
        </section>

        <p className="max-w-xl text-sm text-muted">{t('training.importHint')}</p>

        {exercises.data && exercises.data.length > 1 && <MergeExercises exercises={exercises.data} />}
      </div>
    </>
  )
}
