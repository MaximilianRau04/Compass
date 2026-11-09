import type { CalendarEvent, Task } from '../../api/types'
import { useI18n } from '../../i18n/context'
import { AREA_BG, clockTime, isOverdue, shortTime } from '../../lib/format'
import { useEventStyle } from './eventStyle'

/** A task inside a calendar cell: a hollow ring (it can be ticked off) in the colour of its area. */
export function TaskChip({ task, day, today, onOpen }: { task: Task; day: string; today: string; onOpen: (task: Task) => void }) {
  const overdue = isOverdue(task, today)
  const deadline = task.due_date === day
  const color = task.area ? AREA_BG[task.area.color] : undefined
  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      title={task.title}
      className={[
        'flex w-full min-w-0 items-center gap-1.5 rounded px-1 py-0.5 text-left text-data leading-tight hover:bg-ink/5',
        overdue ? 'text-signal' : '',
      ].join(' ')}
    >
      <span
        className={[
          'grid h-2.5 w-2.5 shrink-0 place-items-center rounded-full border-[1.5px]',
          overdue ? 'border-signal' : task.priority === 'urgent' ? 'border-signal' : 'border-muted',
        ].join(' ')}
      >
        {color && <span className={`h-1 w-1 rounded-full ${color}`} />}
      </span>
      {deadline && task.due_time && <span className="shrink-0 font-mono text-3xs text-muted">{shortTime(task.due_time)}</span>}
      <span className={['truncate', deadline ? 'font-medium' : ''].join(' ')}>{task.title}</span>
    </button>
  )
}

/** A calendar entry in a month cell: coloured dot, start time, title. */
export function EventChip({ event, onOpen }: { event: CalendarEvent; onOpen: (event: CalendarEvent) => void }) {
  const { locale } = useI18n()
  const style = useEventStyle()
  return (
    <button
      type="button"
      onClick={() => onOpen(event)}
      title={event.title}
      className="flex w-full min-w-0 items-center gap-1.5 rounded px-1 py-0.5 text-left text-data leading-tight hover:bg-ink/5"
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${style(event).dot}`} />
      {!event.all_day && <span className="shrink-0 font-mono text-3xs text-muted">{clockTime(event.starts_at, locale)}</span>}
      <span className="truncate">{event.title}</span>
    </button>
  )
}
