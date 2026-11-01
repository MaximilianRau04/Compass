import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { useImportNutrition, useNutritionSummary, useSetGoal, useWeights } from '../api/nutrition'
import { useTodayDate } from '../api/tasks'
import type { GoalMetric, NutritionAverages, NutritionDay, NutritionSummary } from '../api/types'
import { ColumnChart, LineChart } from '../components/charts'
import { DataTable, Stat } from '../components/DataBlocks'
import { BodyPanel } from '../components/BodyPanel'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { decimal, parseDate, pill, rangeDays, relativeDay } from '../lib/format'
import { grams, kcal, nutritionImportMessage } from '../lib/nutrition'

const RANGES = [7, 30, 90]
// kcal per gram, for the share of calories per macro.
const MACROS = [
  { key: 'protein_g', label: 'nutrition.protein', kcal: 4 },
  { key: 'carbs_g', label: 'nutrition.carbs', kcal: 4 },
  { key: 'fat_g', label: 'nutrition.fat', kcal: 9 },
] as const

function ImportButton() {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const upload = useImportNutrition()
  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".zip,.csv,application/zip,text/csv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file) return
          upload.mutate(file, {
            onSuccess: (result) => toast(nutritionImportMessage(result, t)),
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
        {upload.isPending ? t('nutrition.importing') : t('nutrition.import')}
      </button>
    </>
  )
}

/** A value against its goal as a thin bar; past the goal the bar is simply full. */
function GoalBar({ label, value, goal, format }: { label: string; value: number | null; goal?: number; format: (v: number) => string }) {
  const { t } = useI18n()
  return (
    <div>
      <p className="flex items-baseline justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="font-mono text-[12px] tabular-nums">
          <span className="font-medium">{value === null ? '–' : format(value)}</span>
          <span className="text-muted"> {goal ? t('nutrition.ofGoal', { goal: format(goal) }) : `· ${t('nutrition.noGoal')}`}</span>
        </span>
      </p>
      {goal !== undefined && (
        <div className="mt-1 h-2 rounded-full bg-rule/70" role="presentation">
          <div className="h-2 rounded-full bg-chart" style={{ width: `${Math.min(100, ((value ?? 0) / goal) * 100)}%` }} />
        </div>
      )}
    </div>
  )
}

function DayCard({ day, goals, today }: { day: NutritionDay; goals: NutritionSummary['goals']; today: string }) {
  const { t, locale } = useI18n()
  const isToday = day.date === today
  return (
    <section className="mb-8 rounded-md border border-rule bg-paper-raised px-4 py-3">
      <p className="text-xs text-muted">
        {isToday ? t('nutrition.today') : `${t('nutrition.lastDay')} · ${relativeDay(day.date, today, t, locale)}`}
        <span className="ml-2 font-mono text-[11px]">{t(`nutrition.source.${day.source}` as MessageKey)}</span>
        {day.flags.map((flag) => (
          <span key={flag} className="ml-2 rounded-full border border-brass/60 px-1.5 py-px font-mono text-[10px] text-brass">
            {t(`nutrition.flag.${flag}`)}
          </span>
        ))}
      </p>
      <div className="mt-2 space-y-3">
        <GoalBar label={t('nutrition.kcal')} value={day.kcal} goal={goals.kcal} format={(v) => kcal(v, locale)} />
        <GoalBar label={t('nutrition.protein')} value={day.protein_g} goal={goals.protein_g} format={grams} />
      </div>
      <p className="mt-3 font-mono text-[12px] text-muted">
        {t('nutrition.carbs')} {day.carbs_g === null ? '–' : grams(day.carbs_g)} · {t('nutrition.fat')}{' '}
        {day.fat_g === null ? '–' : grams(day.fat_g)}
        {day.fiber_g !== null && ` · ${t('nutrition.fiber')} ${grams(day.fiber_g)}`}
      </p>
      <Micros values={day} className="mt-1" />
      <ul className="mt-3 divide-y divide-rule/60 text-sm">
        {day.meals.map((m) => (
          <li key={m.meal} className="flex justify-between gap-3 py-1.5">
            <span>{t(`nutrition.meal.${m.meal}` as MessageKey)}</span>
            <span className="font-mono text-[12px] text-muted tabular-nums">
              {kcal(m.kcal, locale)}
              {m.protein_g !== null && ` · ${grams(m.protein_g)} ${t('nutrition.protein')}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

const MICROS: { key: keyof NutritionAverages; label: MessageKey; unit: string }[] = [
  { key: 'sugar_g', label: 'nutrition.sugar', unit: 'g' },
  { key: 'saturated_fat_g', label: 'nutrition.saturated', unit: 'g' },
  { key: 'sodium_mg', label: 'nutrition.sodium', unit: 'mg' },
  { key: 'potassium_mg', label: 'nutrition.potassium', unit: 'mg' },
  { key: 'calcium_mg', label: 'nutrition.calcium', unit: 'mg' },
  { key: 'iron_mg', label: 'nutrition.iron', unit: 'mg' },
]

/** Sugar, saturated fat and minerals; only the ones that were logged. */
function Micros({ values, className = '' }: { values: Partial<Record<keyof NutritionAverages, number | null>>; className?: string }) {
  const { t, locale } = useI18n()
  const present = MICROS.filter((m) => values[m.key] != null)
  if (present.length === 0) return null
  return (
    <p className={`font-mono text-[12px] text-muted ${className}`}>
      {present.map((m) => `${t(m.label)} ${decimal(values[m.key] as number, locale)} ${m.unit}`).join(' · ')}
    </p>
  )
}

/** Which days the averages leave out, and the average with them. */
function Quality({ data }: { data: NutritionSummary }) {
  const { t, locale } = useI18n()
  const q = data.quality
  const parts = [
    q.incomplete.length ? t('nutrition.qIncomplete', { n: q.incomplete.length }) : null,
    q.same_as_previous_day.length ? t('nutrition.qSame', { n: q.same_as_previous_day.length }) : null,
    q.gaps.length ? t('nutrition.qGaps', { n: q.gaps.length }) : null,
  ].filter(Boolean)
  if (parts.length === 0) return null
  return (
    <p className="-mt-5 mb-8 font-mono text-[11px] text-muted">
      {t('nutrition.qLeftOut', { list: parts.join(' · ') })}
      {data.averages_all.kcal !== null && data.averages_all.kcal !== data.averages.kcal && ` ${t('nutrition.qWithThem', { kcal: kcal(data.averages_all.kcal, locale) })}`}
    </p>
  )
}

function MacroAverages({ averages }: { averages: NutritionSummary['averages'] }) {
  const { t } = useI18n()
  const values = MACROS.map((m) => ({ ...m, g: averages[m.key] }))
  if (values.every((v) => v.g === null)) return null
  const total = values.reduce((sum, v) => sum + (v.g ?? 0) * v.kcal, 0) || 1
  const max = Math.max(...values.map((v) => (v.g ?? 0) * v.kcal), 1)
  return (
    <section>
      <SectionLabel>{t('nutrition.macros')}</SectionLabel>
      <p className="mt-1 font-mono text-[11px] text-muted">{t('nutrition.macrosHint')}</p>
      <ul className="mt-3 space-y-2">
        {values.map((v) => (
          <li key={v.key} className="grid grid-cols-[7rem_1fr_6.5rem] items-center gap-3 text-sm">
            <span>{t(v.label)}</span>
            <span className="h-3">
              {v.g !== null && v.g > 0 && (
                <span className="block h-3 rounded-r-[4px] bg-chart" style={{ width: `${((v.g * v.kcal) / max) * 100}%` }} />
              )}
            </span>
            <span className="text-right font-mono text-[12px] tabular-nums">
              {v.g === null ? '–' : t('nutrition.macroShare', { g: grams(v.g), pct: Math.round(((v.g * v.kcal) / total) * 100) })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Goals({ goals }: { goals: NutritionSummary['goals'] }) {
  const { t } = useI18n()
  const save = useSetGoal()
  const [values, setValues] = useState<Partial<Record<GoalMetric, string>>>({})
  const fields: { metric: GoalMetric; label: MessageKey }[] = [
    { metric: 'kcal', label: 'nutrition.goalKcal' },
    { metric: 'protein_g', label: 'nutrition.goalProtein' },
    { metric: 'fat_g', label: 'nutrition.goalFat' },
    { metric: 'steps', label: 'nutrition.goalSteps' },
    { metric: 'weight_loss_min', label: 'nutrition.goalLossMin' },
    { metric: 'weight_loss_max', label: 'nutrition.goalLossMax' },
    { metric: 'hr_max', label: 'nutrition.goalHrMax' },
  ]
  return (
    <section>
      <SectionLabel>{t('nutrition.goals')}</SectionLabel>
      <p className="mt-1 mb-3 font-mono text-[11px] text-muted">{t('nutrition.goalsHint')}</p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          const changed = fields.filter(({ metric }) => {
            const v = Number(values[metric])
            return values[metric] !== undefined && v > 0 && v !== goals[metric]
          })
          changed.forEach(({ metric }) =>
            save.mutate(
              { metric, value: Number(values[metric]) },
              { onSuccess: () => toast(t('nutrition.saved')), onError: (error) => toast.error(error.message) },
            ),
          )
          setValues({})
        }}
      >
        {fields.map(({ metric, label }) => (
          <label key={metric} className="text-sm">
            <span className="mb-1 block text-xs text-muted">{t(label)}</span>
            <input
              type="number"
              inputMode="decimal"
              min={0}
              step="any"
              value={values[metric] ?? goals[metric] ?? ''}
              onChange={(e) => setValues({ ...values, [metric]: e.target.value })}
              className="w-32 rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono focus:border-brass focus:outline-none"
            />
          </label>
        ))}
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-md border border-brass px-3 py-1.5 text-sm text-brass hover:bg-brass/10 disabled:opacity-50"
        >
          {t('nutrition.save')}
        </button>
      </form>
    </section>
  )
}

function Weight() {
  const { t, locale } = useI18n()
  const weights = useWeights()
  if (!weights.data?.length) return null
  const points = weights.data.map((w) => ({ key: w.date, date: w.date, value: w.kg }))
  const long = (d: string) => parseDate(d).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
  return (
    <section>
      <SectionLabel>{t('nutrition.weight')}</SectionLabel>
      <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('nutrition.weightHint')}</p>
      <LineChart
        data={points}
        gapDays={45}
        format={(v) => `${decimal(v, locale)} kg`}
        ariaLabel={t('nutrition.weight')}
        tooltip={(p) => (
          <>
            <strong className="font-semibold">{decimal(p.value, locale)} kg</strong>
            <span className="ml-2 text-muted">{long(p.date)}</span>
          </>
        )}
      />
      <DataTable head={[t('training.date'), t('sleep.value')]} rows={[...points].reverse().map((p) => [long(p.date), `${decimal(p.value, locale)} kg`])} />
    </section>
  )
}

export function NutritionPage() {
  const { t, locale } = useI18n()
  const [range, setRange] = useState(30)
  const summary = useNutritionSummary(range)
  const today = useTodayDate()

  const header = (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('nutrition.title')}</h1>
      <ImportButton />
    </header>
  )

  if (summary.error) return <>{header}<p className="text-signal">{t('nutrition.loadError', { message: summary.error.message })}</p></>
  if (summary.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const data = summary.data
  const last = data.days[data.days.length - 1]
  if (!last && !data.weight) {
    return (
      <>
        {header}
        <p className="max-w-md text-muted">{t('nutrition.empty')}</p>
        <div className="mt-10">
          <Goals goals={data.goals} />
        </div>
      </>
    )
  }

  const byDate = new Map(data.days.map((d) => [d.date, d]))
  const days = rangeDays(data.since, data.until)
  const dayLabel = (d: string) => parseDate(d).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })
  const longLabel = (d: string) => parseDate(d).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })
  const kcalBars = days.map((d) => ({ key: d, value: byDate.get(d)?.kcal ?? 0, label: dayLabel(d) }))
  const proteinBars = days.map((d) => ({ key: d, value: byDate.get(d)?.protein_g ?? 0, label: dayLabel(d) }))
  const complete = data.days.filter((d) => d.date < today).length
  const avg = data.averages

  const dayTooltip = (key: string, value: (d: NutritionDay) => string) => {
    const d = byDate.get(key)
    if (!d) return <span className="text-muted">{longLabel(key)} · {t('sleep.noData')}</span>
    return (
      <>
        <strong className="font-semibold">{value(d)}</strong>
        <span className="ml-2 text-muted">
          {longLabel(key)}
          {d.meals.map((m) => ` · ${t(`nutrition.meal.${m.meal}` as MessageKey)} ${Math.round(m.kcal)}`)}
        </span>
      </>
    )
  }

  return (
    <>
      {header}

      {last && <DayCard day={last} goals={data.goals} today={today} />}

      <div className="mb-4 flex justify-end">
        <div role="group" aria-label={t('sleep.range')} className="flex gap-1.5">
          {RANGES.map((n) => (
            <button key={n} type="button" className={pill(range === n)} aria-pressed={range === n} onClick={() => setRange(n)}>
              {t('sleep.daysN', { n })}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label={t('nutrition.avgKcal')} value={avg.kcal === null ? '–' : kcal(avg.kcal, locale)} note={t('nutrition.validDays', { n: data.quality.valid_days, total: complete })} />
        <Stat label={t('nutrition.avgProtein')} value={avg.protein_g === null ? '–' : grams(avg.protein_g)} />
        <Stat
          label={t('nutrition.proteinGoalDays')}
          value={data.protein_goal_days === null ? '–' : t('nutrition.proteinGoalDaysValue', { n: data.protein_goal_days, total: data.quality.valid_days })}
        />
        <Stat
          label={t('nutrition.weight')}
          value={data.weight ? `${decimal(data.weight.kg, locale)} kg` : '–'}
          note={
            data.weight_change !== null
              ? t('nutrition.weightChange', { change: `${data.weight_change > 0 ? '+' : ''}${decimal(data.weight_change, locale)}`, n: range })
              : data.weight
                ? relativeDay(data.weight.date, today, t, locale)
                : undefined
          }
        />
      </div>

      <Quality data={data} />

      <div className="space-y-10">
        <section>
          <SectionLabel>{t('nutrition.kcalPerDay')}</SectionLabel>
          <p className="mt-1 mb-2 font-mono text-[11px] text-muted">{t('nutrition.perDayHint')}</p>
          <ColumnChart
            data={kcalBars}
            format={(v) => Math.round(v).toLocaleString(locale)}
            ariaLabel={t('nutrition.kcalPerDay')}
            target={data.goals.kcal ? { value: data.goals.kcal, label: t('nutrition.goal', { value: kcal(data.goals.kcal, locale) }) } : undefined}
            tooltip={(b) => dayTooltip(b.key, (d) => kcal(d.kcal, locale))}
          />
          <DataTable
            head={[t('nutrition.day'), t('nutrition.kcal')]}
            rows={[...data.days].reverse().map((d) => [longLabel(d.date), kcal(d.kcal, locale)])}
          />
        </section>

        {proteinBars.some((b) => b.value > 0) && (
          <section>
            <SectionLabel>{t('nutrition.proteinPerDay')}</SectionLabel>
            <div className="mt-3">
              <ColumnChart
                data={proteinBars}
                format={(v) => grams(v)}
                ariaLabel={t('nutrition.proteinPerDay')}
                target={data.goals.protein_g ? { value: data.goals.protein_g, label: t('nutrition.goal', { value: grams(data.goals.protein_g) }) } : undefined}
                tooltip={(b) => dayTooltip(b.key, (d) => (d.protein_g === null ? '–' : grams(d.protein_g)))}
              />
            </div>
            <DataTable
              head={[t('nutrition.day'), t('nutrition.protein')]}
              rows={[...data.days].reverse().map((d) => [longLabel(d.date), d.protein_g === null ? '–' : grams(d.protein_g)])}
            />
          </section>
        )}

        <MacroAverages averages={avg} />
        <Micros values={avg} className="-mt-6" />

        <BodyPanel />

        <Weight />

        <Goals goals={data.goals} />

        <p className="max-w-xl text-sm text-muted">{t('nutrition.importHint')}</p>
      </div>
    </>
  )
}
