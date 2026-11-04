import { type CSSProperties, useEffect, useState } from 'react'

import type { CalendarEvent, Task } from '../api/types'
import { useI18n } from '../i18n/context'
import { clockTime } from '../lib/format'
import { useEventStyle } from './calendar/eventStyle'

const HOUR = 3_600_000

/** The current time, refreshed every minute. */
function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])
  return now
}

/**
 * The day as a course line: from waking up to the evening, today's events are waypoints on it,
 * tasks with a due time are buoys, and a brass marker shows where the day stands. The part already
 * sailed is drawn solid, the rest dashed.
 */
export function CourseLine({ today, events, tasks, wakeAt }: { today: string; events: CalendarEvent[]; tasks: Task[]; wakeAt: string | null }) {
  const { t, locale } = useI18n()
  const style = useEventStyle()
  const now = useNow()

  const midnight = new Date(`${today}T00:00`).getTime()
  const timed = events
    .filter((e) => !e.all_day)
    .map((e) => {
      const start = new Date(e.starts_at).getTime()
      const end = e.ends_at ? new Date(e.ends_at).getTime() : start
      return { event: e, start, end: Math.max(end, start) }
    })
    .filter((e) => e.end >= midnight && e.start < midnight + 24 * HOUR)
    .sort((a, b) => a.start - b.start)
  const buoys = tasks
    .filter((task) => task.due_date === today && task.due_time)
    .map((task) => ({ task, at: new Date(`${today}T${task.due_time!.slice(0, 5)}`).getTime() }))

  const wake = wakeAt ? new Date(wakeAt).getTime() : null
  const firstMark = Math.min(wake ?? midnight + 7 * HOUR, ...timed.map((e) => e.start), ...buoys.map((b) => b.at))
  const lastMark = Math.max(midnight + 22 * HOUR, ...timed.map((e) => e.end), ...buoys.map((b) => b.at))
  const t0 = Math.max(midnight, Math.floor(firstMark / HOUR) * HOUR)
  const t1 = Math.min(midnight + 26 * HOUR, Math.ceil(lastMark / HOUR) * HOUR)
  const pct = (time: number) => Math.min(100, Math.max(0, ((time - t0) / (t1 - t0)) * 100))
  const nowPct = pct(now)

  const span = (t1 - t0) / HOUR
  const every = span > 16 ? 3 : 2
  const hours = Array.from({ length: Math.floor(span) + 1 }, (_, i) => t0 + i * HOUR)

  // The event under way, else the next one: the only waypoint with a label, to keep it calm.
  const focus = timed.find((e) => e.end > now) ?? null
  const time = (ms: number) => clockTime(new Date(ms).toISOString(), locale)
  const summary = [
    t('course.label', { from: time(t0), to: time(t1), now: time(now) }),
    focus ? t(focus.start <= now ? 'course.current' : 'course.next', { time: time(focus.start), title: focus.event.title }) : null,
  ]
    .filter(Boolean)
    .join(', ')

  const focusPct = focus ? Math.min(88, Math.max(12, pct(focus.start))) : 0

  return (
    <div role="img" aria-label={summary} className="relative h-[4.25rem] select-none">
      <div aria-hidden>
        {/* Label of the current or next waypoint, above the line. */}
        {focus && (
          <span
            className="absolute top-0 max-w-[60%] -translate-x-1/2 truncate font-mono text-[11px] text-ink"
            style={{ left: `${focusPct}%` }}
          >
            <span className="text-muted">{time(focus.start)}</span> {focus.event.title}
          </span>
        )}

        {/* The course: solid where the day has passed, dashed ahead. */}
        <span className="absolute top-[1.65rem] left-0 h-0 w-full -translate-y-1/2 border-t-2 border-dashed border-rule" />
        <span
          className="fill-in absolute top-[1.65rem] left-0 h-0.5 -translate-y-1/2 rounded-full bg-brass"
          style={{ width: `${nowPct}%`, animationDelay: '200ms' }}
        />

        {/* Hour ticks and labels. */}
        {hours.map((h) => {
          const labelled = (new Date(h).getHours() % every) === 0
          return (
            <span key={h} className="absolute top-[1.95rem] -translate-x-1/2" style={{ left: `${pct(h)}%` }}>
              <span className={`mx-auto block w-px bg-rule ${labelled ? 'h-1.5' : 'h-1'}`} />
              {labelled && <span className="mt-1 block font-mono text-[10px] text-muted tabular-nums">{String(new Date(h).getHours()).padStart(2, '0')}</span>}
            </span>
          )
        })}

        {/* Waypoints: one bar per event, faded once passed. */}
        {timed.map(({ event, start, end }, i) => {
          const left = pct(start)
          const passed = end <= now
          return (
            <span
              key={event.id}
              title={`${time(start)} ${event.title}`}
              className={`rise absolute top-[1.65rem] h-2 min-w-2 -translate-y-1/2 rounded-full ring-2 ring-paper ${style(event).dot} ${passed ? 'opacity-40' : ''}`}
              style={{ left: `${left}%`, width: `${Math.max(0, pct(end) - left)}%`, '--i': 3 + i } as CSSProperties}
            />
          )
        })}

        {/* Buoys: tasks due at a set time. */}
        {buoys.map(({ task, at }) => {
          const done = task.status === 'done'
          const late = !done && at < now
          return (
            <span
              key={task.id}
              title={`${time(at)} ${task.title}`}
              className={[
                'absolute top-[1.65rem] h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-2',
                done ? 'border-sea bg-sea' : late ? 'border-signal bg-paper' : 'border-brass bg-paper',
              ].join(' ')}
              style={{ left: `${pct(at)}%` }}
            />
          )
        })}

        {/* Wake-up mark at the start of the course. */}
        {wake !== null && wake >= t0 && (
          <span className="absolute top-[0.85rem] -translate-x-1/2 font-mono text-[10px] leading-none text-muted" style={{ left: `${pct(wake)}%` }}>
            ↑
          </span>
        )}

        {/* Where the day stands. */}
        {now >= t0 && now <= t1 && (
          <>
            <span
              className="absolute top-[0.95rem] h-0 w-0 -translate-x-1/2 border-x-[5px] border-t-[7px] border-x-transparent border-t-brass transition-[left] duration-1000"
              style={{ left: `${nowPct}%` }}
            />
            <span
              className="absolute top-[1.65rem] h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-paper bg-brass shadow-[0_0_0_3px_color-mix(in_srgb,var(--brass)_25%,transparent)] transition-[left] duration-1000"
              style={{ left: `${nowPct}%` }}
            />
          </>
        )}
      </div>
    </div>
  )
}
