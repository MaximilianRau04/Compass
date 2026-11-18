import type { CalendarEvent, Task } from '../api/types'
import { useI18n } from '../i18n/context'
import { eventsOn, tasksOn } from '../lib/calendar'
import { addDays, eventOnDay, longDate, relativeDay } from '../lib/format'
import { EventItem } from './EventItem'
import { SectionLabel } from './Layout'
import { TaskItem } from './TaskItem'

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
