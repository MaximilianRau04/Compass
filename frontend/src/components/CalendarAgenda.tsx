import { toast } from 'sonner'

import { useIntegrations, useSyncCalendars } from '../api/calendar'
import { useTodayDate } from '../api/tasks'
import type { CalendarEvent, Task } from '../api/types'
import { useI18n } from '../i18n/context'
import { eventsOn, tasksOn } from '../lib/calendar'
import { addDays, eventOnDay, longDate, relativeDay } from '../lib/format'
import { EventItem } from './EventItem'
import { SectionLabel } from './Layout'
import { SyncIssue } from './SyncIssue'
import { TaskItem } from './TaskItem'

export function SyncStatus() {
  const { t, locale } = useI18n()
  const states = useIntegrations().data?.filter((s) => s.name.startsWith('calendar:')) ?? []
  const sync = useSyncCalendars()
  const today = useTodayDate()

  const run = () =>
    sync.mutate(undefined, {
      onSuccess: () => toast(t('cal.synced')),
      onError: (error) => toast.error(error.message),
    })

  return (
    <div className="mt-10 space-y-1 border-t border-rule pt-3 font-mono text-2xs text-muted">
      {states.length === 0 && <p>{t('cal.noFeeds')}</p>}
      {states.map((state) => {
        const name = state.name.replace('calendar:', '')
        if (state.last_error) return <SyncIssue key={state.name} name={name} error={state.last_error} lastSuccess={state.last_success_at} today={today} />
        return (
          <p key={state.name}>
            {state.last_success_at &&
              t('cal.lastSync', {
                name,
                time: new Date(state.last_success_at).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }),
              })}
          </p>
        )
      })}
      <button type="button" onClick={run} disabled={sync.isPending} className="text-brass hover:underline disabled:opacity-50">
        {t('cal.sync')}
      </button>
    </div>
  )
}

/** One day as a list: calendar entries first (they have fixed times), then the day's tasks. */
export function DayList({
  day,
  today,
  events,
  tasks,
  onOpen,
  onOpenEvent,
}: {
  day: string
  today: string
  events: CalendarEvent[]
  tasks: Task[]
  onOpen: (task: Task) => void
  onOpenEvent?: (event: CalendarEvent) => void
}) {
  const { t, locale } = useI18n()
  const { weekday, date } = longDate(day, locale)
  const relative = relativeDay(day, today, t, locale)
  const dayEvents = eventsOn(events, day)
  const dayTasks = tasksOn(tasks, day)
  return (
    <section>
      <SectionLabel>{`${weekday} · ${date}${day === today || day === addDays(today, 1) ? ` · ${relative}` : ''}`}</SectionLabel>
      {dayEvents.length === 0 && dayTasks.length === 0 && <p className="py-3 text-sm text-muted">{t('cal.dayEmpty')}</p>}
      <ul className="divide-y divide-rule/60">
        {dayEvents.map((event) => (
          <EventItem key={event.id} event={event} onOpen={onOpenEvent} />
        ))}
        {dayTasks.map((task) => (
          <TaskItem key={task.id} task={task} today={today} onOpen={onOpen} />
        ))}
      </ul>
    </section>
  )
}

/** A stretch of days as an agenda: only days with entries, plus today and overdue tasks. */
export function CalendarAgenda({
  days,
  events,
  tasks,
  today,
  onOpen,
  onOpenEvent,
}: {
  days: string[]
  events: CalendarEvent[]
  tasks: Task[]
  today: string
  onOpen: (task: Task) => void
  onOpenEvent: (event: CalendarEvent) => void
}) {
  const { t } = useI18n()
  const showsToday = days.includes(today)
  const overdue = showsToday ? tasks.filter((task) => task.due_date && task.due_date < today) : []
  const filled = days.filter(
    (day) => day === today || events.some((event) => eventOnDay(event, day)) || tasksOn(tasks, day).length > 0,
  )

  if (overdue.length === 0 && filled.length === 0) return <p className="text-muted">{t('cal.empty')}</p>

  return (
    <div className="space-y-8">
      {overdue.length > 0 && (
        <section>
          <SectionLabel count={overdue.length} tone="signal">
            {t('bucket.overdue')}
          </SectionLabel>
          <ul className="divide-y divide-rule/60">
            {overdue.map((task) => (
              <TaskItem key={task.id} task={task} today={today} onOpen={onOpen} />
            ))}
          </ul>
        </section>
      )}
      {filled.map((day) => (
        <DayList key={day} day={day} today={today} events={events} tasks={tasks} onOpen={onOpen} onOpenEvent={onOpenEvent} />
      ))}
    </div>
  )
}
