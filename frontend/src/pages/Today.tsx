import { type CSSProperties, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'

import { useJournalDay } from '../api/journal'
import { useMailOverview } from '../api/mail'
import { useBriefs, useNewsOverview, useTodayBrief } from '../api/news'
import { useNutritionSummary } from '../api/nutrition'
import { useSetup } from '../api/setup'
import { useBedtime, useDayHeartRate, useHealthSummary, useReadiness } from '../api/sleep'
import { useToday } from '../api/tasks'
import { usePlannedWorkouts, useTrainingSummary } from '../api/training'
import type { Brief, MailOverview, NewsOverview, Task } from '../api/types'
import { BodyTiles } from '../components/BodyTiles'
import { CompassDial } from '../components/CompassDial'
import { CourseLine } from '../components/CourseLine'
import { EventItem } from '../components/EventItem'
import { SectionLabel } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { MoveTask } from '../components/MoveTask'
import { QuickAdd } from '../components/QuickAdd'
import { TaskItem } from '../components/TaskItem'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { shortPart } from '../lib/brief'
import { addDays, clockTime, isLeftBehind, longDate, relativeDay, toIsoDate } from '../lib/format'
import { pageTitle } from '../lib/ui'

/** Important mails of the last two weeks: count and the newest three. */
function ImportantMail({ overview }: { overview: MailOverview | undefined }) {
  const { t } = useI18n()
  if (!overview || overview.important === 0) return null
  return (
    <section className="rise" style={{ '--i': 6 } as CSSProperties}>
      <Link to="/mail" className="block hover:text-ink">
        <SectionLabel count={overview.important}>{t('today.mail')}</SectionLabel>
      </Link>
      <p className="mt-1 font-mono text-2xs text-muted">
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

/** In the evening: the latest bedtime before tomorrow's first event. */
function Bedtime() {
  const { t, locale } = useI18n()
  const [evening] = useState(() => new Date().getHours() >= 16)
  const bedtime = useBedtime(evening)
  const b = bedtime.data
  if (!evening || !b?.event || !b.latest_bedtime || !b.wake_at) return null
  return (
    <section className="rise flex items-baseline gap-3 rounded-lg border border-rule bg-paper-raised px-4 py-3" style={{ '--i': 2 } as CSSProperties}>
      <span aria-hidden className="text-brass">☾</span>
      <p>
        <span className="font-medium">{t('bedtime.latest', { time: clockTime(b.latest_bedtime, locale) })}</span>
        <span className="block font-mono text-2xs text-muted">
          {t(b.capped ? 'bedtime.capped' : 'bedtime.because', {
            time: clockTime(b.event.starts_at, locale),
            title: b.event.title,
            wake: clockTime(b.wake_at, locale),
            sleep: ((b.sleep_need_minutes ?? 0) / 60).toLocaleString(locale),
            fall: b.fall_asleep_minutes ?? 0,
          })}
        </span>
      </p>
    </section>
  )
}

/** Today's readiness by fixed rules, with what took points off. Hidden without a score. */
function ReadinessCard() {
  const { t } = useI18n()
  const r = useReadiness().data
  if (!r || r.score === null || !r.level) return null
  const tone = r.level === 'good' ? 'text-sea' : r.level === 'low' ? 'text-signal' : 'text-brass'
  return (
    <section className="rise flex items-baseline gap-3 rounded-lg border border-rule bg-paper-raised px-4 py-3" style={{ '--i': 2 } as CSSProperties}>
      <span aria-hidden className={tone}>●</span>
      <p>
        <span className="font-medium">{t('readiness.title', { score: r.score })}</span> <span>{t(`readiness.${r.level}`)}</span>
        {r.reasons.length > 0 && <span className="block font-mono text-2xs text-muted">{r.reasons.map((reason) => t(`readiness.${reason}`)).join(' · ')}</span>}
      </p>
    </section>
  )
}

/** Workouts planned on today's weekday (Training, template editor), struck through once done. */
function PlannedWorkouts() {
  const { t } = useI18n()
  const planned = usePlannedWorkouts()
  if (!planned.data?.length) return null
  return (
    <section className="rise flex items-baseline gap-3 rounded-lg border border-rule bg-paper-raised px-4 py-3" style={{ '--i': 2 } as CSSProperties}>
      <span aria-hidden className="text-brass">◆</span>
      <p className="min-w-0 flex-1">
        <span className="font-medium">{t('today.plannedWorkout')} </span>
        {planned.data.map((w, i) => (
          <span key={w.id} className={w.done ? 'text-muted line-through' : ''}>
            {i > 0 && ', '}
            {w.name}
          </span>
        ))}
      </p>
      {planned.data.some((w) => !w.done) && (
        <Link to="/training/log" className="font-mono text-2xs text-brass hover:underline">
          {t('today.startWorkout')} →
        </Link>
      )}
    </section>
  )
}

/** In the evening: a link to today's journal entry, or its mood and energy once written. */
function JournalPrompt({ today }: { today: string }) {
  const { t } = useI18n()
  const [evening] = useState(() => new Date().getHours() >= 18)
  const day = useJournalDay(today, evening)
  if (!evening || !day.data) return null
  const entry = day.data.entry
  return (
    <Link to="/journal" className="rise flex items-baseline gap-3 rounded-lg border border-rule px-4 py-3 hover:border-ink" style={{ '--i': 2 } as CSSProperties}>
      <span aria-hidden className="text-brass">✎</span>
      <span className={entry ? 'text-muted' : 'font-medium'}>
        {entry ? t('today.journalDone', { mood: entry.mood ?? '–', energy: entry.energy ?? '–' }) : t('today.journal')}
      </span>
    </Link>
  )
}

/** The daily brief a routine saved this morning; folded away once read. */
function DailyBrief({ brief }: { brief: Brief | null | undefined }) {
  const { t, locale } = useI18n()
  if (!brief) return null
  return (
    <details open className="rise rounded-md border border-rule bg-paper-raised px-4 py-3" style={{ '--i': 3 } as CSSProperties}>
      <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
        <span className="font-display text-label font-semibold tracking-[0.18em] text-muted uppercase">{brief.title ?? t('today.brief')}</span>
        <span className="font-mono text-2xs text-muted">{clockTime(brief.updated_at, locale)}</span>
      </summary>
      <Markdown text={brief.body} className="mt-2" />
    </details>
  )
}

/** Today's texts of other routines (any kind but the daily brief and the news report), plus the
 * newest weekly review until the next one comes (it is saved on Sundays, the push links here). */
function OtherBriefs({ briefs, weekly, today }: { briefs: Brief[] | undefined; weekly: Brief | undefined; today: string }) {
  const { t, locale } = useI18n()
  const others = (briefs ?? []).filter(
    (b) => b.local_date === today && b.kind !== 'daily' && b.kind !== 'news' && b.kind !== 'weekly',
  )
  if (weekly && weekly.local_date >= addDays(today, -6)) others.unshift(weekly)
  if (others.length === 0) return null
  return (
    <div className="space-y-2">
      {others.map((brief) => (
        <details key={brief.id} className="rounded-md border border-rule px-4 py-3">
          <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
            <span className="font-display text-label font-semibold tracking-[0.18em] text-muted uppercase">{brief.title ?? brief.kind}</span>
            <span className="font-mono text-2xs text-muted">
              {brief.local_date === today ? clockTime(brief.updated_at, locale) : relativeDay(brief.local_date, today, t, locale)}
            </span>
          </summary>
          <Markdown text={brief.body} className="mt-2" />
        </details>
      ))}
    </div>
  )
}

/** The short part of the news report (from today or yesterday); without one, the three
 * best personal news items of the last 36 hours. */
function TopNews({ overview, today }: { overview: NewsOverview | undefined; today: string }) {
  const { t } = useI18n()
  const report = overview?.report
  if (report && report.local_date >= addDays(today, -1)) {
    const short = shortPart(report.body)
    if (short) {
      return (
        <section className="rise" style={{ '--i': 7 } as CSSProperties}>
          <Link to="/news" className="block hover:text-ink">
            <SectionLabel>{t('today.news')}</SectionLabel>
          </Link>
          <Markdown text={short} className="mt-2 text-input" />
          <Link to="/news" className="mt-2 inline-block font-mono text-2xs text-brass hover:underline">
            {t('today.newsReport')} →
          </Link>
        </section>
      )
    }
  }
  if (!overview || overview.top.length === 0) return null
  return (
    <section className="rise" style={{ '--i': 7 } as CSSProperties}>
      <Link to="/news" className="block hover:text-ink">
        <SectionLabel>{t('today.news')}</SectionLabel>
      </Link>
      <ul className="mt-1 divide-y divide-rule/60">
        {overview.top.map((item) => (
          <li key={item.id} className="py-2">
            <a href={item.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:text-brass">
              {item.title}
            </a>
            <span className="font-mono text-2xs text-muted"> · {item.feed}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function TodayPage() {
  const { t, locale } = useI18n()
  const { data, isPending, isFetching, error } = useToday()
  const health = useHealthSummary(7)
  const heart = useDayHeartRate()
  const food = useNutritionSummary(7)
  const training = useTrainingSummary(8)
  const mail = useMailOverview()
  const brief = useTodayBrief()
  const briefs = useBriefs()
  const weekly = useBriefs('weekly', 1)
  const news = useNewsOverview()
  const setup = useSetup()
  const [open, setOpen] = useState<Task | null>(null)
  const [params] = useSearchParams()
  const [deviceDay] = useState(() => toIsoDate(new Date()))

  if (setup.data?.first_run) return <Navigate to="/welcome" replace />
  if (error) return <p className="text-signal">{t('common.apiUnreachable', { message: error.message })}</p>
  // A stored answer from an earlier day would show yesterday's tasks for a moment; wait for today's.
  const yesterday = data !== undefined && data.today !== deviceDay && isFetching
  if (isPending || yesterday) return <p className="font-mono text-sm text-muted">{t('common.loading')}</p>

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
      <header className="rise mb-2 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-muted">{date}</p>
          <h1 className={pageTitle}>
            {weekday}
          </h1>
        </div>
        <CompassDial done={data.done_today.length} total={active + data.done_today.length} />
      </header>

      <div className="rise mb-8" style={{ '--i': 1 } as CSSProperties}>
        <CourseLine
          today={today}
          events={data.events}
          tasks={[...data.overdue, ...data.due_today, ...data.done_today]}
          wakeAt={health.data?.last_night?.local_date === today ? health.data.last_night.end_at : null}
        />
      </div>

      {/* Phone: tiles, the day, then mail and news. Desktop: the day on the left, the body and
          the inbox on the right. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,25rem)] lg:grid-rows-[auto_1fr]">
        <div className="lg:col-start-2 lg:row-start-1">
          <BodyTiles today={today} health={health.data} heart={heart.data} food={food.data} training={training.data} />
        </div>

        <div className="space-y-8 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <div className="fixed inset-x-0 bottom-[calc(3.6rem+env(safe-area-inset-bottom))] z-20 px-3 sm:static sm:px-0">
            <QuickAdd today={today} autoFocus={params.get('new') === '1' || params.get('neu') === '1'} />
          </div>

          <Bedtime />
          <ReadinessCard />
          <PlannedWorkouts />
          <JournalPrompt today={today} />
          <DailyBrief brief={brief.data} />
          <OtherBriefs briefs={briefs.data} weekly={weekly.data?.[0]} today={today} />

          {visible.length === 0 && data.done_today.length === 0 && data.events.length === 0 && (
            <p className="max-w-md text-muted">
              {emptyBefore}
              <code className="font-mono text-ink">{t('today.emptyCode')}</code>
              {emptyAfter}
            </p>
          )}

          {data.events.length > 0 && (
            <section className="rise" style={{ '--i': 4 } as CSSProperties}>
              <SectionLabel count={data.events.length}>{t('today.events')}</SectionLabel>
              <ul className="divide-y divide-rule/60">
                {data.events.map((event) => (
                  <EventItem key={event.id} event={event} />
                ))}
              </ul>
            </section>
          )}

          {visible.map((section, i) => (
            <section key={section.key} className="rise" style={{ '--i': 5 + i } as CSSProperties}>
              <SectionLabel count={section.tasks.length} tone={section.tone}>
                {t(section.label)}
              </SectionLabel>
              <ul className="divide-y divide-rule/60">
                {section.tasks.map((task) => (
                  <TaskItem key={task.id} task={task} today={today} onOpen={setOpen}>
                    {isLeftBehind(task, today) && <MoveTask task={task} today={today} targets={['today', 'tomorrow']} />}
                  </TaskItem>
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

        <div className="space-y-8 lg:col-start-2 lg:row-start-2">
          <ImportantMail overview={mail.data} />
          <TopNews overview={news.data} today={today} />
        </div>
      </div>

      <TaskSheet task={open} onClose={() => setOpen(null)} />
    </>
  )
}
