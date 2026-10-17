import type { CalendarEvent } from '../api/types'
import { useI18n } from '../i18n/context'
import { eventTime } from '../lib/format'

/** A calendar entry: read-only, so no checkbox, just the time slot on the left. */
export function EventItem({ event }: { event: CalendarEvent }) {
  const { t, locale } = useI18n()
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span className="mt-0.5 w-[5.5rem] shrink-0 font-mono text-[12px] text-muted tabular-nums">
        {eventTime(event, t, locale)}
      </span>
      <div className="min-w-0 flex-1 border-l-2 border-chart/60 pl-3">
        <span className="block leading-snug">{event.title}</span>
        <span className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
          {event.location && <span>{event.location}</span>}
          <span className="uppercase">{event.feed}</span>
        </span>
      </div>
    </li>
  )
}
