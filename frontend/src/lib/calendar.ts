import type { CalendarEvent, Task } from '../api/types'
import { addDays, eventOnDay, parseDate, toIsoDate } from './format'

/** Monday of the week that contains the day. */
export function weekStart(day: string): string {
  const offset = (parseDate(day).getDay() + 6) % 7
  return addDays(day, -offset)
}

/** Monday of the week after the day. */
export function nextWeekStart(day: string): string {
  return addDays(weekStart(day), 7)
}

export function monthStart(day: string): string {
  return `${day.slice(0, 7)}-01`
}

export function addMonths(day: string, months: number): string {
  const date = parseDate(monthStart(day))
  date.setMonth(date.getMonth() + months)
  return toIsoDate(date)
}

/** The full weeks (Monday to Sunday) that cover the month of the day. */
export function monthGrid(day: string): string[] {
  const first = monthStart(day)
  const last = addDays(addMonths(first, 1), -1)
  const start = weekStart(first)
  const end = addDays(weekStart(last), 6)
  const days: string[] = []
  for (let d = start; d <= end; d = addDays(d, 1)) days.push(d)
  return days
}

/** ISO 8601 week number. */
export function isoWeek(day: string): number {
  const date = parseDate(day)
  // The Thursday of this week decides which year the week belongs to.
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7))
  const firstThursday = new Date(date.getFullYear(), 0, 4)
  return 1 + Math.round(((date.getTime() - firstThursday.getTime()) / 86_400_000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7)
}

/** Events of a day in reading order: all-day entries first, then by start time. */
export function eventsOn(events: CalendarEvent[], day: string): CalendarEvent[] {
  return events
    .filter((event) => eventOnDay(event, day))
    .sort((a, b) => Number(b.all_day) - Number(a.all_day) || a.starts_at.localeCompare(b.starts_at))
}

/** Tasks that belong on a day: by deadline, or by planned day when the deadline is elsewhere. */
export function tasksOn(tasks: Task[], day: string): Task[] {
  return tasks.filter((task) => task.due_date === day || (task.scheduled_date === day && task.due_date !== day))
}

export interface Placed {
  event: CalendarEvent
  /** Minutes since midnight, clipped to the day. */
  start: number
  end: number
  column: number
  columns: number
}

const MIN_DURATION = 30

/**
 * Timed events of one day with their position in the grid. Overlapping events share the width:
 * each cluster of overlaps gets as many columns as it needs at its busiest point.
 */
export function layoutDay(events: CalendarEvent[], day: string): Placed[] {
  const dayStart = parseDate(day).getTime()
  const dayEnd = parseDate(addDays(day, 1)).getTime()
  const items = events
    .filter((event) => !event.all_day)
    .map((event) => {
      const from = new Date(event.starts_at).getTime()
      const to = event.ends_at ? new Date(event.ends_at).getTime() : from
      return { event, from, to }
    })
    .filter(({ from, to }) => from < dayEnd && (to > dayStart || (from >= dayStart && to === from)))
    .map(({ event, from, to }) => {
      const start = Math.max(0, (from - dayStart) / 60_000)
      const end = Math.min(24 * 60, Math.max((to - dayStart) / 60_000, start + MIN_DURATION))
      return { event, start, end, column: 0, columns: 1 }
    })
    .sort((a, b) => a.start - b.start || b.end - a.end)

  let cluster: Placed[] = []
  let clusterEnd = -1
  const columnEnds: number[] = []
  const close = () => {
    for (const item of cluster) item.columns = columnEnds.length
    cluster = []
    columnEnds.length = 0
  }
  for (const item of items) {
    if (item.start >= clusterEnd) close()
    let column = columnEnds.findIndex((end) => end <= item.start)
    if (column === -1) column = columnEnds.push(0) - 1
    columnEnds[column] = item.end
    item.column = column
    cluster.push(item)
    clusterEnd = Math.max(clusterEnd, item.end)
  }
  close()
  return items
}
