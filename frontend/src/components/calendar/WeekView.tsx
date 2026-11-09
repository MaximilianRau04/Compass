import { useEffect, useState } from 'react'

import type { CalendarEvent, Task } from '../../api/types'
import { useI18n } from '../../i18n/context'
import { eventsOn, layoutDay, tasksOn } from '../../lib/calendar'
import { clockTime, parseDate } from '../../lib/format'
import { EventChip, TaskChip } from './Chips'
import { useEventStyle } from './eventStyle'

const HOUR_PX = 48
const DEFAULT_FROM = 8
const DEFAULT_TO = 19

function useMinuteOfDay(): number {
  const read = () => {
    const now = new Date()
    return now.getHours() * 60 + now.getMinutes()
  }
  const [minute, setMinute] = useState(read)
  useEffect(() => {
    const id = setInterval(() => setMinute(read()), 60_000)
    return () => clearInterval(id)
  }, [])
  return minute
}

/** Days side by side with an hour grid; all-day entries and tasks sit in a lane above it. */
export function WeekView({
  days,
  events,
  tasks,
  today,
  selected,
  onSelect,
  onOpenTask,
  onOpenEvent,
}: {
  days: string[]
  events: CalendarEvent[]
  tasks: Task[]
  today: string
  /** The day listed below the grid; tapping a day's header selects it. */
  selected: string
  onSelect: (day: string) => void
  onOpenTask: (task: Task) => void
  onOpenEvent: (event: CalendarEvent) => void
}) {
  const { locale } = useI18n()
  const style = useEventStyle()
  const now = useMinuteOfDay()
  const placed = days.map((day) => layoutDay(events, day))

  // Office hours by default, stretched to fit the earliest and latest entry of the visible days.
  const all = placed.flat()
  const from = Math.min(DEFAULT_FROM, ...all.map((p) => Math.floor(p.start / 60)))
  const to = Math.max(DEFAULT_TO, ...all.map((p) => Math.ceil(p.end / 60)))
  const hours = Array.from({ length: to - from }, (_, i) => from + i)
  const top = (minute: number) => ((minute - from * 60) / 60) * HOUR_PX

  const columns = { gridTemplateColumns: `2.75rem repeat(${days.length}, minmax(0, 1fr))` }
  const lanes = days.map((day) => ({
    events: eventsOn(events, day).filter((event) => event.all_day),
    tasks: tasksOn(tasks, day),
  }))
  const hasLane = lanes.some((lane) => lane.events.length > 0 || lane.tasks.length > 0)

  return (
    <div className="rounded-lg border border-rule bg-paper-raised/60">
      <div className="sticky top-0 z-10 grid rounded-t-lg border-b border-rule bg-paper-raised" style={columns}>
        <span />
        {days.map((day) => {
          const date = parseDate(day)
          const isToday = day === today
          return (
            <button
              key={day}
              type="button"
              aria-pressed={day === selected}
              aria-label={date.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
              onClick={() => onSelect(day)}
              className={['border-l border-rule px-1 py-2 text-center transition-colors', day === selected ? 'bg-brass/10' : 'hover:bg-ink/[0.04]'].join(' ')}
            >
              <span className={['block font-display text-data tracking-[0.16em] uppercase', isToday ? 'text-brass' : 'text-muted'].join(' ')}>
                {date.toLocaleDateString(locale, { weekday: 'short' })}
              </span>
              <span
                className={[
                  'mx-auto mt-0.5 grid h-8 w-8 place-items-center rounded-full font-mono text-input tabular-nums',
                  isToday ? 'bg-brass font-medium text-brass-ink' : day < today ? 'text-muted' : 'text-ink',
                ].join(' ')}
              >
                {date.getDate()}
              </span>
            </button>
          )
        })}
      </div>

      {hasLane && (
        <div className="grid border-b border-rule" style={columns}>
          <span />
          {lanes.map((lane, i) => (
            <div key={days[i]} className="min-w-0 space-y-0.5 border-l border-rule p-1">
              {lane.events.map((event) => (
                <EventChip key={event.id} event={event} onOpen={onOpenEvent} />
              ))}
              {lane.tasks.map((task) => (
                <TaskChip key={task.id} task={task} day={days[i]} today={today} onOpen={onOpenTask} />
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="grid" style={columns}>
        <div className="relative" style={{ height: hours.length * HOUR_PX }}>
          {hours.map((hour) => (
            <span
              key={hour}
              className="absolute right-1.5 -translate-y-1/2 font-mono text-3xs text-muted tabular-nums"
              style={{ top: top(hour * 60) }}
            >
              {hour > from && `${String(hour).padStart(2, '0')}:00`}
            </span>
          ))}
        </div>
        {days.map((day, i) => (
          // Tapping free space in a column selects the day too; events open themselves.
          <div
            key={day}
            onClick={() => onSelect(day)}
            className={['relative cursor-pointer border-l border-rule', day === selected ? 'bg-brass/[0.07]' : day === today ? 'bg-brass/[0.04]' : ''].join(' ')}
          >
            {hours.map((hour) => (
              <div key={hour} className="border-t border-rule/50 first:border-t-0" style={{ height: HOUR_PX }} />
            ))}
            {placed[i].map(({ event, start, end, column, columns: count }) => {
              const height = ((end - start) / 60) * HOUR_PX
              return (
                <button
                  key={`${event.id}-${day}`}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpenEvent(event)
                  }}
                  title={event.title}
                  className={`absolute overflow-hidden rounded-[5px] border-l-[3px] px-1.5 py-1 text-left text-data leading-tight text-ink transition-shadow hover:z-10 hover:shadow-md ${style(event).block} ${day < today ? 'opacity-60' : ''}`}
                  style={{
                    top: top(start) + 1,
                    height: Math.max(height - 2, 18),
                    left: `calc(${(column / count) * 100}% + 2px)`,
                    width: `calc(${100 / count}% - 4px)`,
                  }}
                >
                  <span className="line-clamp-2 font-medium">{event.title}</span>
                  {height >= 40 && (
                    <span className="mt-0.5 block truncate font-mono text-3xs text-muted">
                      {clockTime(event.starts_at, locale)}
                      {event.location && ` · ${event.location}`}
                    </span>
                  )}
                </button>
              )
            })}
            {day === today && now >= from * 60 && now <= to * 60 && (
              <div className="pointer-events-none absolute inset-x-0 z-20" style={{ top: top(now) }} aria-hidden>
                <div className="relative h-0.5 bg-signal">
                  <span className="absolute -top-[3px] -left-[4px] h-2 w-2 rounded-full bg-signal" />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
