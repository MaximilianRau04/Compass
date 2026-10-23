import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useMailOverview } from '../api/mail'
import { useBriefs, useNewsOverview, useTodayBrief } from '../api/news'
import { useNutritionSummary } from '../api/nutrition'
import { useDayHeartRate, useHealthSummary } from '../api/sleep'
import { useToday } from '../api/tasks'
import { useTrainingSummary } from '../api/training'
import type { Brief, MailOverview, NewsOverview, Task } from '../api/types'
import { BodyTiles } from '../components/BodyTiles'
import { CompassDial } from '../components/CompassDial'
import { EventItem } from '../components/EventItem'
import { SectionLabel } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { QuickAdd } from '../components/QuickAdd'
import { TaskItem } from '../components/TaskItem'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { shortPart } from '../lib/brief'
import { addDays, clockTime, longDate } from '../lib/format'

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

/** The daily brief a Claude routine saved this morning; folded away once read. */
function DailyBrief({ brief }: { brief: Brief | null | undefined }) {
  const { t, locale } = useI18n()
  if (!brief) return null
  return (
    <details open className="rounded-md border border-rule bg-paper-raised px-4 py-3">
      <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
        <span className="font-display text-[13px] font-semibold tracking-[0.18em] text-muted uppercase">{brief.title ?? t('today.brief')}</span>
        <span className="font-mono text-[11px] text-muted">{clockTime(brief.updated_at, locale)}</span>
      </summary>
      <Markdown text={brief.body} className="mt-2" />
    </details>
  )
}

/** Today's texts of other routines (any kind but the daily brief and the news report). */
function OtherBriefs({ briefs, today }: { briefs: Brief[] | undefined; today: string }) {
  const { locale } = useI18n()
  const others = (briefs ?? []).filter((b) => b.local_date === today && b.kind !== 'daily' && b.kind !== 'news')
  if (others.length === 0) return null
  return (
    <div className="space-y-2">
      {others.map((brief) => (
        <details key={brief.id} className="rounded-md border border-rule px-4 py-3">
          <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
            <span className="font-display text-[13px] font-semibold tracking-[0.18em] text-muted uppercase">{brief.title ?? brief.kind}</span>
            <span className="font-mono text-[11px] text-muted">{clockTime(brief.updated_at, locale)}</span>
          </summary>
          <Markdown text={brief.body} className="mt-2" />
        </details>
      ))}
    </div>
  )
}

/** The short part of Claude's news report (from today or yesterday); without one, the three
 * best personal news items of the last 36 hours. */
function TopNews({ overview, today }: { overview: NewsOverview | undefined; today: string }) {
  const { t } = useI18n()
  const report = overview?.report
  if (report && report.local_date >= addDays(today, -1)) {
    const short = shortPart(report.body)
    if (short) {
      return (
        <section>
          <Link to="/news" className="block hover:text-ink">
            <SectionLabel>{t('today.news')}</SectionLabel>
          </Link>
          <Markdown text={short} className="mt-2 text-[15px]" />
          <Link to="/news" className="mt-2 inline-block font-mono text-[11px] text-brass hover:underline">
            {t('today.newsReport')} →
          </Link>
        </section>
      )
    }
  }
  if (!overview || overview.top.length === 0) return null
  return (
    <section>
      <Link to="/news" className="block hover:text-ink">
        <SectionLabel>{t('today.news')}</SectionLabel>
      </Link>
      <ul className="mt-1 divide-y divide-rule/60">
        {overview.top.map((item) => (
          <li key={item.id} className="py-2">
            <a href={item.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:text-brass">
              {item.title}
            </a>
            <span className="font-mono text-[11px] text-muted"> · {item.feed}</span>
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
  const heart = useDayHeartRate()
  const food = useNutritionSummary(7)
  const training = useTrainingSummary(8)
  const mail = useMailOverview()
  const brief = useTodayBrief()
  const briefs = useBriefs()
  const news = useNewsOverview()
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

      {/* Phone: tiles, the day, then mail and news. Desktop: the day on the left, the body and
          the inbox on the right. */}
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,25rem)] lg:grid-rows-[auto_1fr]">
        <div className="lg:col-start-2 lg:row-start-1">
          <BodyTiles today={today} health={health.data} heart={heart.data} food={food.data} training={training.data} />
        </div>

        <div className="space-y-8 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <div className="fixed inset-x-0 bottom-[calc(3.6rem+env(safe-area-inset-bottom))] z-20 px-3 sm:static sm:px-0">
            <QuickAdd today={today} autoFocus={params.get('neu') === '1'} />
          </div>

          <DailyBrief brief={brief.data} />
          <OtherBriefs briefs={briefs.data} today={today} />

          {visible.length === 0 && data.done_today.length === 0 && data.events.length === 0 && (
            <p className="max-w-md text-muted">
              {emptyBefore}
              <code className="font-mono text-ink">{t('today.emptyCode')}</code>
              {emptyAfter}
            </p>
          )}

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

        <div className="space-y-8 lg:col-start-2 lg:row-start-2">
          <ImportantMail overview={mail.data} />
          <TopNews overview={news.data} today={today} />
        </div>
      </div>

      <TaskSheet task={open} onClose={() => setOpen(null)} />
    </>
  )
}
