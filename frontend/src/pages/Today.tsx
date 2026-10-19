import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useMailOverview } from '../api/mail'
import { useNutritionSummary } from '../api/nutrition'
import { useHealthSummary } from '../api/sleep'
import { useToday } from '../api/tasks'
import type { HealthSummary, MailOverview, NutritionSummary, Task } from '../api/types'
import { CompassDial } from '../components/CompassDial'
import { EventItem } from '../components/EventItem'
import { SectionLabel } from '../components/Layout'
import { QuickAdd } from '../components/QuickAdd'
import { TaskItem } from '../components/TaskItem'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { addDays, clockTime, longDate } from '../lib/format'
import { hours } from '../lib/health'
import { grams, kcal } from '../lib/nutrition'

/** Last night's sleep in one line, only while it is current (woke up today or yesterday). */
function LastNight({ summary, today }: { summary: HealthSummary | undefined; today: string }) {
  const { t, locale } = useI18n()
  const night = summary?.last_night
  if (!night || night.local_date < addDays(today, -1)) return null
  const resting = summary.days.find((d) => d.date === night.local_date)?.resting_hr
  return (
    <Link to="/schlaf" className="block rounded-md border border-rule bg-paper-raised px-3 py-2.5 hover:border-ink">
      <span className="text-xs text-muted">{t('today.lastNight')}</span>
      <span className="mt-0.5 flex flex-wrap items-baseline gap-x-3">
        <span className="text-2xl font-semibold">{hours(night.asleep_minutes)}</span>
        <span className="font-mono text-[12px] text-muted">
          {clockTime(night.start_at, locale)}–{clockTime(night.end_at, locale)}
          {resting != null && ` · ${t('today.restingHr', { bpm: resting })}`}
        </span>
      </span>
    </Link>
  )
}

/** Calories and protein logged today against the goals; hidden until something is logged. */
function NutritionToday({ summary, today }: { summary: NutritionSummary | undefined; today: string }) {
  const { t, locale } = useI18n()
  const day = summary?.days.find((d) => d.date === today)
  if (!summary || !day) return null
  const { kcal: kcalGoal, protein_g: proteinGoal } = summary.goals
  return (
    <Link to="/ernaehrung" className="block rounded-md border border-rule bg-paper-raised px-3 py-2.5 hover:border-ink">
      <span className="text-xs text-muted">{t('today.nutrition')}</span>
      <span className="mt-0.5 flex flex-wrap items-baseline gap-x-3">
        <span className="text-2xl font-semibold">{kcal(day.kcal, locale)}</span>
        <span className="font-mono text-[12px] text-muted">
          {kcalGoal && `${t('nutrition.ofGoal', { goal: Math.round(kcalGoal).toLocaleString(locale) })} · `}
          {day.protein_g !== null && t('today.protein', { g: grams(day.protein_g) })}
          {day.protein_g !== null && proteinGoal && ` / ${grams(proteinGoal)}`}
        </span>
      </span>
    </Link>
  )
}

/** Important mails of the last two weeks: count and the newest three. */
function ImportantMail({ overview }: { overview: MailOverview | undefined }) {
  const { t } = useI18n()
  if (!overview || overview.important === 0) return null
  return (
    <section>
      <Link to="/mail" className="block hover:text-ink">
        <SectionLabel count={overview.important}>{t('today.mail')}</SectionLabel>
      </Link>
      <p className="mt-1 font-mono text-[11px] text-muted">
        {t('today.mailCount', { n: overview.important, unread: overview.unread_important })}
      </p>
      <ul className="mt-1 divide-y divide-rule/60">
        {overview.top.map((m) => (
          <li key={m.id} className="py-2">
            <Link to="/mail" className="block">
              <span className={m.seen ? '' : 'font-semibold'}>{m.from_name ?? m.from_addr}</span>
              <span className="text-muted"> · {m.subject}</span>
              {m.summary && <span className="block truncate text-sm text-muted">{m.summary}</span>}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function TodayPage() {
  const { t, locale } = useI18n()
  const { data, isPending, error } = useToday()
  const health = useHealthSummary(7)
  const food = useNutritionSummary(7)
  const mail = useMailOverview()
  const [open, setOpen] = useState<Task | null>(null)
  const [params] = useSearchParams()

  if (error) return <p className="text-signal">{t('common.apiUnreachable', { message: error.message })}</p>
  if (isPending) return <p className="font-mono text-sm text-muted">{t('common.loading')}</p>

  const today = data.today
  const { weekday, date } = longDate(today, locale)
  const active = data.overdue.length + data.due_today.length + data.scheduled.length
  const sections: { key: string; label: MessageKey; tasks: Task[]; tone?: 'signal' }[] = [
    { key: 'overdue', label: 'today.overdue', tasks: data.overdue, tone: 'signal' },
    { key: 'due', label: 'today.dueToday', tasks: data.due_today },
    { key: 'scheduled', label: 'today.scheduled', tasks: data.scheduled },
    { key: 'upcoming', label: 'today.upcoming', tasks: data.upcoming },
  ]
  const visible = sections.filter((s) => s.tasks.length > 0)
  // Without vars, t() keeps the {code} placeholder, so the inline code element can go in between.
  const [emptyBefore, emptyAfter] = t('today.empty').split('{code}')

  return (
    <>
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-muted">{date}</p>
          <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">
            {weekday}
          </h1>
        </div>
        <CompassDial done={data.done_today.length} total={active + data.done_today.length} />
      </header>

      <div className="fixed inset-x-0 bottom-[calc(3.6rem+env(safe-area-inset-bottom))] z-20 px-3 sm:static sm:mb-8 sm:px-0">
        <QuickAdd today={today} autoFocus={params.get('neu') === '1'} />
      </div>

      {visible.length === 0 && data.done_today.length === 0 && data.events.length === 0 && (
        <p className="mb-8 max-w-md text-muted">
          {emptyBefore}
          <code className="font-mono text-ink">{t('today.emptyCode')}</code>
          {emptyAfter}
        </p>
      )}

      <div className="space-y-8">
        <div className="grid gap-2 empty:hidden sm:grid-cols-2">
          <LastNight summary={health.data} today={today} />
          <NutritionToday summary={food.data} today={today} />
        </div>

        <ImportantMail overview={mail.data} />

        {data.events.length > 0 && (
          <section>
            <SectionLabel count={data.events.length}>{t('today.events')}</SectionLabel>
            <ul className="divide-y divide-rule/60">
              {data.events.map((event) => (
                <EventItem key={event.id} event={event} />
              ))}
            </ul>
          </section>
        )}

        {visible.map((section) => (
          <section key={section.key}>
            <SectionLabel count={section.tasks.length} tone={section.tone}>
              {t(section.label)}
            </SectionLabel>
            <ul className="divide-y divide-rule/60">
              {section.tasks.map((task) => (
                <TaskItem key={task.id} task={task} today={today} onOpen={setOpen} />
              ))}
            </ul>
          </section>
        ))}

        {data.done_today.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer list-none">
              <SectionLabel count={data.done_today.length}>{t('today.doneToday')}</SectionLabel>
            </summary>
            <ul className="divide-y divide-rule/60">
              {data.done_today.map((task) => (
                <TaskItem key={task.id} task={task} today={today} onOpen={setOpen} />
              ))}
            </ul>
          </details>
        )}
      </div>

      <TaskSheet task={open} onClose={() => setOpen(null)} />
    </>
  )
}
