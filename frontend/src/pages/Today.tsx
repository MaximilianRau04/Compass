import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useToday } from '../api/tasks'
import type { Task } from '../api/types'
import { CompassDial } from '../components/CompassDial'
import { EventItem } from '../components/EventItem'
import { SectionLabel } from '../components/Layout'
import { QuickAdd } from '../components/QuickAdd'
import { TaskItem } from '../components/TaskItem'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { longDate } from '../lib/format'

export function TodayPage() {
  const { t, locale } = useI18n()
  const { data, isPending, error } = useToday()
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
        <p className="max-w-md text-muted">
          {emptyBefore}
          <code className="font-mono text-ink">{t('today.emptyCode')}</code>
          {emptyAfter}
        </p>
      )}

      <div className="space-y-8">
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
