import { useState } from 'react'
import { toast } from 'sonner'

import { useCalendar, useIntegrations, useSyncCalendars } from '../api/calendar'
import type { Task } from '../api/types'
import { useI18n } from '../i18n/context'
import { addDays, eventOnDay, longDate, relativeDay } from '../lib/format'
import { EventItem } from './EventItem'
import { SectionLabel } from './Layout'
import { TaskItem } from './TaskItem'

const DAYS = 14

function SyncStatus() {
  const { t, locale } = useI18n()
  const states = useIntegrations().data?.filter((s) => s.name.startsWith('calendar:')) ?? []
  const sync = useSyncCalendars()

  const run = () =>
    sync.mutate(undefined, {
      onSuccess: () => toast(t('cal.synced')),
      onError: (error) => toast.error(error.message),
    })

  return (
    <div className="mt-10 space-y-1 border-t border-rule pt-3 font-mono text-[11px] text-muted">
      {states.length === 0 && <p>{t('cal.noFeeds')}</p>}
      {states.map((state) => {
        const name = state.name.replace('calendar:', '')
        return (
          <p key={state.name} className={state.last_error ? 'text-signal' : ''}>
            {state.last_error
              ? t('cal.syncError', { name, error: state.last_error })
              : state.last_success_at &&
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

/** Two weeks as an agenda: calendar events and tasks by deadline or planned day. */
export function CalendarAgenda({ tasks, today, onOpen }: { tasks: Task[]; today: string; onOpen: (task: Task) => void }) {
  const { t, locale } = useI18n()
  const [start, setStart] = useState(today)
  const end = addDays(start, DAYS - 1)
  const events = useCalendar(start, end)

  const days = Array.from({ length: DAYS }, (_, i) => addDays(start, i))
  const showsToday = start <= today && today <= end
  const overdue = showsToday ? tasks.filter((task) => task.due_date && task.due_date < today) : []
  const tasksOn = (day: string) =>
    tasks.filter((task) => task.due_date === day || (task.scheduled_date === day && task.due_date !== day))

  const filled = days
    .map((day) => ({
      day,
      events: (events.data ?? []).filter((event) => eventOnDay(event, day)),
      tasks: tasksOn(day),
    }))
    .filter((d) => d.day === today || d.events.length > 0 || d.tasks.length > 0)
  const empty = overdue.length === 0 && filled.every((d) => d.events.length === 0 && d.tasks.length === 0)

  const nav = 'rounded-full border border-rule px-3 py-1 text-sm text-muted hover:border-ink hover:text-ink'
  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs text-muted">
          {longDate(start, locale).date} – {longDate(end, locale).date}
        </p>
        <div className="flex gap-1.5">
          <button type="button" className={nav} onClick={() => setStart(addDays(start, -DAYS))}>
            {t('cal.prev')}
          </button>
          {!showsToday && (
            <button type="button" className={nav} onClick={() => setStart(today)}>
              {t('cal.backToToday')}
            </button>
          )}
          <button type="button" className={nav} onClick={() => setStart(addDays(start, DAYS))}>
            {t('cal.next')}
          </button>
        </div>
      </div>

      {events.error && <p className="mb-4 text-signal">{t('cal.loadError', { message: events.error.message })}</p>}
      {empty && events.isSuccess && <p className="text-muted">{t('cal.empty')}</p>}

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

        {filled.map(({ day, events: dayEvents, tasks: dayTasks }) => {
          const { weekday, date } = longDate(day, locale)
          const relative = relativeDay(day, today, t, locale)
          return (
            <section key={day}>
              <SectionLabel>{`${weekday} · ${date}${day === today || day === addDays(today, 1) ? ` · ${relative}` : ''}`}</SectionLabel>
              <ul className="divide-y divide-rule/60">
                {dayEvents.map((event) => (
                  <EventItem key={event.id} event={event} />
                ))}
                {dayTasks.map((task) => (
                  <TaskItem key={task.id} task={task} today={today} onOpen={onOpen} />
                ))}
              </ul>
            </section>
          )
        })}
      </div>

      <SyncStatus />
    </>
  )
}
