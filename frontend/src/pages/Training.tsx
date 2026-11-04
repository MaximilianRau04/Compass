import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { useTodayDate } from '../api/tasks'
import {
  useExercises,
  useImportWorkouts,
  useMergeExercise,
  useProgress,
  useProgression,
  useSessionDetail,
  useSessions,
  useTrainingSummary,
  useUpdateExercise,
} from '../api/training'
import type { Exercise, ProgressPoint, SessionBrief, Split, Suggestion } from '../api/types'
import { ColumnChart, LineChart } from '../components/charts'
import { DataTable, Stat } from '../components/DataBlocks'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { compact, decimal, localDay, parseDate, pill, relativeDay } from '../lib/format'
import { importMessage } from '../lib/training'
import { loadDraft } from '../lib/workout'

const WEEKS = 12
const SPLITS: Split[] = ['push', 'pull', 'legs', 'other', 'sport']
type Metric = 'best_e1rm' | 'top_weight' | 'max_reps' | 'volume_kg'

function ImportButton() {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const upload = useImportWorkouts()
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
        color="var(--m-training)"
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

/** Rep range and weight step of one exercise, edited in place. */
function RangeEditor({ suggestion }: { suggestion: Suggestion }) {
  const { t } = useI18n()
  const update = useUpdateExercise()
  const [min, setMin] = useState(String(suggestion.rep_min))
  const [max, setMax] = useState(String(suggestion.rep_max))
  const [step, setStep] = useState(String(suggestion.weight_step))
  const input = 'w-14 rounded-md border border-rule bg-paper px-2 py-1 text-center font-mono text-[13px]'
  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate(
          { id: suggestion.exercise_id, data: { rep_min: Number(min), rep_max: Number(max), weight_step: Number(step.replace(',', '.')) } },
          { onSuccess: () => toast(t('progress.saved')), onError: (error) => toast.error(error.message) },
        )
      }}
    >
      <input value={min} onChange={(e) => setMin(e.target.value)} inputMode="numeric" aria-label={t('progress.repMin')} className={input} />
      <span className="text-muted">–</span>
      <input value={max} onChange={(e) => setMax(e.target.value)} inputMode="numeric" aria-label={t('progress.repMax')} className={input} />
      <span className="text-muted">{t('progress.reps')}</span>
      <input value={step} onChange={(e) => setStep(e.target.value)} inputMode="decimal" aria-label={t('progress.step')} className={input} />
      <span className="text-muted">{t('progress.stepUnit')}</span>
      <button type="submit" disabled={update.isPending} className="rounded-md border border-rule px-2 py-1 hover:border-ink disabled:opacity-50">
        {t('progress.save')}
      </button>
    </form>
  )
}

/** The next target per exercise (double progression) and the exercises that stagnate. */
function NextTargets() {
  const { t, locale } = useI18n()
  const progression = useProgression()
  const [all, setAll] = useState(false)
  const list = progression.data?.suggestions ?? []
  if (list.length === 0) return null
  const shown = all ? list : list.slice(0, 8)
  const sets = (s: Suggestion) =>
    s.last_sets.map((x) => `${x.weight_kg != null ? decimal(x.weight_kg, locale) : t('training.bodyweight')}×${x.reps}${x.rir != null ? ` @${x.rir}` : ''}`).join(' · ')
  return (
    <section>
      <SectionLabel count={progression.data?.stagnant.length || undefined} tone={progression.data?.stagnant.length ? 'signal' : undefined}>
        {t('progress.title')}
      </SectionLabel>
      <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('progress.hint')}</p>
      <ul className="divide-y divide-rule/60">
        {shown.map((s) => (
          <li key={s.exercise_id} className="py-2.5">
            <details>
              <summary className="flex cursor-pointer list-none flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <span>
                  <span className="font-medium">{s.name}</span>
                  {s.stagnant && <span className="ml-2 rounded-full border border-signal/60 px-1.5 py-px font-mono text-[10px] text-signal">{t('progress.stagnant', { n: s.same_sessions })}</span>}
                </span>
                <span className={`font-mono text-[12px] tabular-nums ${s.action === 'increase' ? 'text-brass' : ''}`}>
                  {s.weight_kg != null ? `${decimal(s.weight_kg, locale)} kg${s.bodyweight ? ' +' : ''} × ${s.reps}` : `× ${s.reps}`}
                  {s.action === 'increase' ? ' ↑' : ''}
                </span>
                <span className="w-full font-mono text-[11px] text-muted">
                  {t('progress.last', { sets: sets(s) })} · {s.rep_min}–{s.rep_max} · +{decimal(s.weight_step, locale)} kg
                  {!s.rir_known && ` · ${t('progress.noRir')}`}
                </span>
              </summary>
              <RangeEditor suggestion={s} />
            </details>
          </li>
        ))}
      </ul>
      {list.length > 8 && (
        <button type="button" onClick={() => setAll(!all)} className="mt-1 font-mono text-[11px] text-muted hover:text-ink">
          {all ? t('progress.less') : t('progress.all', { n: list.length })}
        </button>
      )}
    </section>
  )
}

function SessionRow({ session, today }: { session: SessionBrief; today: string }) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(false)
  const detail = useSessionDetail(open ? session.id : null)
  const when = relativeDay(localDay(session.started_at), today, t, locale)
  const duration = session.duration_minutes !== null ? `${t('training.duration', { n: session.duration_minutes })} · ` : ''
  // Heart rate from the watch, for logged sessions as well as for workouts tracked only there.
  const heart =
    session.hr_avg !== null
      ? `${t('training.hr', { avg: session.hr_avg, max: session.hr_max ?? '–' })}${session.zone2_minutes ? ` · ${t('zone2.short', { n: session.zone2_minutes })}` : ''} · `
      : ''
  // Known only from Health Connect: name, duration and heart rate, nothing to expand.
  if (session.sets === 0) {
    const watch = session.source === 'watch'
    return (
      <li className="flex items-baseline justify-between gap-3 py-2.5">
        <span>
          <span className="font-medium">{session.workout_name}</span>
          {watch && <span className="ml-2 rounded-full border border-rule px-1.5 py-px font-mono text-[10px] text-muted">{t('split.sport')}</span>}
          <span className="ml-2 font-mono text-[11px] text-muted">{when}</span>
        </span>
        <span className="font-mono text-[11px] text-muted" title={watch ? undefined : t('training.withoutSetsHint')}>
          {duration}
          {heart}
          {watch ? t('training.fromWatch') : t('training.withoutSets')}
        </span>
      </li>
    )
  }
  return (
    <li className="py-2.5">
      <details onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
          <span>
            <span className="font-medium">{session.workout_name}</span>
            <span className="ml-2 font-mono text-[11px] text-muted">{when}</span>
          </span>
          <span className="font-mono text-[11px] text-muted">
            {duration}
            {heart}
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
      <div className="flex flex-wrap gap-2">
        <Link to="/training/log" className="rounded-md bg-brass px-3 py-2 text-sm font-medium text-brass-ink hover:opacity-90">
          {loadDraft() ? t('log.continue') : t('log.startTraining')}
        </Link>
        <ImportButton />
      </div>
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
          note={`${last.workout_name} · ${last.sets ? t('training.setsN', { n: last.sets }) : t('training.withoutSets')}`}
        />
      </div>

      <div className="space-y-10">
        <section>
          <SectionLabel>{t('training.weeklyVolume')}</SectionLabel>
          <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('training.weeklyVolumeHint')}</p>
          <ColumnChart
            color="var(--m-training)"
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
                    {n > 0 && <span className="block h-3 rounded-r-[4px] bg-m-training" style={{ width: `${(n / splitMax) * 100}%` }} />}
                  </span>
                  <span className="text-right font-mono text-[12px] tabular-nums">{n}</span>
                </li>
              )
            })}
          </ul>
        </section>

        <NextTargets />

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
