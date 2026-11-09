import type { CalendarEvent, Task } from '../../api/types'
import { useI18n } from '../../i18n/context'
import { eventsOn, isoWeek, monthGrid, tasksOn } from '../../lib/calendar'
import { AREA_BG, parseDate } from '../../lib/format'
import { EventChip, TaskChip } from './Chips'
import { useEventStyle } from './eventStyle'

const VISIBLE = 3

/**
 * The month as weeks. On wide screens every cell lists its first entries, on phones it shows
 * dots. Tapping a cell selects the day; the page lists the selected day below the grid.
 */
export function MonthView({
  anchor,
  selected,
  events,
  tasks,
  today,
  onSelect,
  onOpenTask,
  onOpenEvent,
}: {
  anchor: string
  selected: string
  events: CalendarEvent[]
  tasks: Task[]
  today: string
  onSelect: (day: string) => void
  onOpenTask: (task: Task) => void
  onOpenEvent: (event: CalendarEvent) => void
}) {
  const { t, locale } = useI18n()
  const style = useEventStyle()
  const days = monthGrid(anchor)
  const month = anchor.slice(0, 7)
  const weeks = Array.from({ length: days.length / 7 }, (_, i) => days.slice(i * 7, i * 7 + 7))
  const weekdays = days.slice(0, 7).map((day) => parseDate(day).toLocaleDateString(locale, { weekday: 'short' }))

  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-paper-raised/60">
      <div className="grid grid-cols-[1.75rem_repeat(7,minmax(0,1fr))] border-b border-rule bg-paper-raised sm:grid-cols-[2.25rem_repeat(7,minmax(0,1fr))]">
        <span />
        {weekdays.map((name) => (
          <span key={name} className="py-2 text-center font-display text-data tracking-[0.16em] text-muted uppercase">
            {name}
          </span>
        ))}
      </div>
      {weeks.map((week) => (
        <div
          key={week[0]}
          className="grid grid-cols-[1.75rem_repeat(7,minmax(0,1fr))] border-b border-rule last:border-b-0 sm:grid-cols-[2.25rem_repeat(7,minmax(0,1fr))]"
        >
          <span className="pt-2 text-center font-mono text-3xs text-muted/70 tabular-nums">{isoWeek(week[0])}</span>
          {week.map((day) => {
            const dayEvents = eventsOn(events, day)
            const dayTasks = tasksOn(tasks, day)
            const count = dayEvents.length + dayTasks.length
            const shownTasks = dayTasks.slice(0, VISIBLE)
            const shownEvents = dayEvents.slice(0, Math.max(0, VISIBLE - shownTasks.length))
            const hidden = count - shownTasks.length - shownEvents.length
            const outside = day.slice(0, 7) !== month
            const isToday = day === today
            return (
              <div
                key={day}
                role="button"
                tabIndex={0}
                aria-pressed={day === selected}
                aria-label={parseDate(day).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })}
                onClick={() => onSelect(day)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect(day)
                  }
                }}
                className={[
                  'min-h-16 min-w-0 cursor-pointer border-l border-rule p-1 transition-colors sm:min-h-28',
                  day === selected ? 'bg-brass/10' : 'hover:bg-ink/[0.03]',
                  outside ? 'bg-paper/70' : '',
                ].join(' ')}
              >
                <span
                  className={[
                    'grid h-6 w-6 place-items-center rounded-full font-mono text-data tabular-nums',
                    isToday ? 'bg-brass font-medium text-brass-ink' : outside ? 'text-muted/60' : day < today ? 'text-muted' : 'text-ink',
                  ].join(' ')}
                >
                  {parseDate(day).getDate()}
                </span>

                {/* Phones: one dot per entry, at most five. */}
                <div className="mt-1 flex flex-wrap gap-0.5 px-0.5 sm:hidden">
                  {[...dayTasks.map((task) => (task.area ? AREA_BG[task.area.color] : 'bg-muted')), ...dayEvents.map((e) => style(e).dot)]
                    .slice(0, 5)
                    .map((color, i) => (
                      <span key={i} className={`h-1.5 w-1.5 rounded-full ${color}`} />
                    ))}
                </div>

                <div className="mt-0.5 hidden space-y-px sm:block" onClick={(e) => e.stopPropagation()}>
                  {shownTasks.map((task) => (
                    <TaskChip key={task.id} task={task} day={day} today={today} onOpen={onOpenTask} />
                  ))}
                  {shownEvents.map((event) => (
                    <EventChip key={event.id} event={event} onOpen={onOpenEvent} />
                  ))}
                  {hidden > 0 && (
                    <button type="button" onClick={() => onSelect(day)} className="px-1 font-mono text-2xs text-brass hover:underline">
                      {t('cal.more', { n: hidden })}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
