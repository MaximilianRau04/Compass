import type { CalendarEvent, Task } from '../api/types'
import type { Translate } from '../i18n/context'

const RRULE_WEEKDAY: Record<string, number> = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 }

/** Parse "YYYY-MM-DD" as a local date (not UTC). */
export function parseDate(value: string): Date {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toIsoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parseDate(to).getTime() - parseDate(from).getTime()) / 86_400_000)
}

/** "today", "tomorrow", "Fri 17 Oct", "3 days ago" … relative to today, in the UI language. */
export function relativeDay(value: string, today: string, t: Translate, locale: string): string {
  const diff = daysBetween(today, value)
  if (diff === 0) return t('date.today')
  if (diff === 1) return t('date.tomorrow')
  if (diff === 2) return t('date.dayAfterTomorrow')
  if (diff === -1) return t('date.yesterday')
  if (diff < -1 && diff > -7) return t('date.daysAgo', { n: -diff })
  const date = parseDate(value)
  const sameYear = date.getFullYear() === parseDate(today).getFullYear()
  return date.toLocaleDateString(locale, {
    weekday: diff > 0 && diff < 7 ? 'short' : undefined,
    day: 'numeric',
    month: locale.startsWith('de') ? 'numeric' : 'short',
    year: sameYear ? undefined : 'numeric',
  })
}

export function shortTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null
}

export function longDate(value: string, locale: string): { weekday: string; date: string } {
  const date = parseDate(value)
  return {
    weekday: date.toLocaleDateString(locale, { weekday: 'long' }),
    date: date.toLocaleDateString(locale, { day: 'numeric', month: 'long' }),
  }
}

/** Short name of a weekday, 0 = Monday (2023-01-02 was a Monday). */
export function shortWeekday(index: number, locale: string): string {
  return new Date(2023, 0, 2 + index).toLocaleDateString(locale, { weekday: 'short' })
}

function weekdayName(code: string, locale: string): string {
  // 2023-01-01 was a Sunday; offset from there to get the weekday's name.
  return new Date(2023, 0, 1 + RRULE_WEEKDAY[code]).toLocaleDateString(locale, { weekday: 'long' })
}

export function recurrenceLabel(rule: string | null, t: Translate, locale: string): string | null {
  if (!rule) return null
  const parts = Object.fromEntries(rule.split(';').map((p) => p.split('=') as [string, string]))
  const n = Number(parts.INTERVAL ?? 1)
  const days = parts.BYDAY?.split(',') ?? []
  if (parts.FREQ === 'DAILY') return n === 1 ? t('recur.daily') : t('recur.everyNDays', { n })
  if (parts.FREQ === 'WEEKLY') {
    if (days.length === 5 && !days.includes('SA') && !days.includes('SU')) return t('recur.weekdays')
    if (days.length === 1 && n === 1) return t('recur.everyWeekday', { day: weekdayName(days[0], locale) })
    return n === 1 ? t('recur.weekly') : t('recur.everyNWeeks', { n })
  }
  if (parts.FREQ === 'MONTHLY') return n === 1 ? t('recur.monthly') : t('recur.everyNMonths', { n })
  if (parts.FREQ === 'YEARLY') return t('recur.yearly')
  return rule
}

export function isOverdue(task: Task, today: string): boolean {
  return task.status !== 'done' && task.status !== 'cancelled' && !!task.due_date && task.due_date < today
}

/** The deadline or the planned day has passed: the task waits for a new day. */
export function isLeftBehind(task: Task, today: string): boolean {
  return isOverdue(task, today) || (task.status !== 'done' && task.status !== 'cancelled' && !!task.scheduled_date && task.scheduled_date < today)
}

export const AREA_TEXT: Record<string, string> = {
  blue: 'text-area-blue',
  violet: 'text-area-violet',
  teal: 'text-area-teal',
  amber: 'text-area-amber',
  rose: 'text-area-rose',
  slate: 'text-area-slate',
}

export const AREA_BG: Record<string, string> = {
  blue: 'bg-area-blue',
  violet: 'bg-area-violet',
  teal: 'bg-area-teal',
  amber: 'bg-area-amber',
  rose: 'bg-area-rose',
  slate: 'bg-area-slate',
}

export function addDays(value: string, days: number): string {
  const date = parseDate(value)
  date.setDate(date.getDate() + days)
  return toIsoDate(date)
}

/** Local calendar day (YYYY-MM-DD) of an ISO timestamp. */
export function localDay(timestamp: string): string {
  return toIsoDate(new Date(timestamp))
}

export function clockTime(timestamp: string, locale: string): string {
  return new Date(timestamp).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
}

/** "14:00–15:30", "all day" or just the start time for point-in-time entries. */
export function eventTime(event: CalendarEvent, t: Translate, locale: string): string {
  if (event.all_day) return t('event.allDay')
  const start = clockTime(event.starts_at, locale)
  if (!event.ends_at || event.ends_at === event.starts_at) return start
  return `${start}–${clockTime(event.ends_at, locale)}`
}

/** Whether an event covers the given local day (all-day ends are exclusive). */
export function eventOnDay(event: CalendarEvent, day: string): boolean {
  const start = localDay(event.starts_at)
  if (!event.ends_at || !event.all_day) return start === day
  return start <= day && day < localDay(event.ends_at)
}

/** 950, 12.3K, 1.2M */
export function compact(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

/** An amount as typed, in the way of the locale or the other one: "1.000,50" and "1,000.50" are
 * the same, and a lone separator before exactly three digits groups thousands ("1,000"). */
export function parseAmount(text: string, locale: string): number {
  const value = text.trim().replace(/[\s'€$£]/g, '')
  const decimalMark = new Intl.NumberFormat(locale).format(1.5).includes(',') ? ',' : '.'
  const last = Math.max(value.lastIndexOf(','), value.lastIndexOf('.'))
  if (last < 0) return Number(value || NaN)
  const mixed = value.includes(',') && value.includes('.')
  const repeated = value.indexOf(value[last]) !== last
  const grouped = !mixed && value[last] !== decimalMark && value.length - last - 1 === 3
  if (repeated || grouped) return Number(value.replace(/[.,]/g, ''))
  return Number(`${value.slice(0, last).replace(/[.,]/g, '')}.${value.slice(last + 1)}`)
}

export function decimal(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)
}

/** Toggle button style for range and metric pickers. */
export const pill = (active: boolean) =>
  [
    'rounded-full border px-3 py-1 text-sm transition-colors',
    active ? 'border-ink bg-ink text-paper' : 'border-rule text-muted hover:border-ink hover:text-ink',
  ].join(' ')

/** Every day of the range, oldest first, so missing days show as gaps and not as zero. */
export function rangeDays(since: string, until: string): string[] {
  return Array.from({ length: daysBetween(since, until) + 1 }, (_, i) => addDays(since, i))
}
