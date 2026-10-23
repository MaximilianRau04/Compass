import { useAreas } from '../../api/tasks'
import type { CalendarEvent } from '../../api/types'

interface Style {
  block: string
  border: string
  dot: string
}

// Full class names so Tailwind finds them; one per area colour.
const AREA_STYLES: Record<string, Style> = {
  blue: { block: 'border-area-blue bg-area-blue/12', border: 'border-area-blue', dot: 'bg-area-blue' },
  violet: { block: 'border-area-violet bg-area-violet/12', border: 'border-area-violet', dot: 'bg-area-violet' },
  teal: { block: 'border-area-teal bg-area-teal/12', border: 'border-area-teal', dot: 'bg-area-teal' },
  amber: { block: 'border-area-amber bg-area-amber/12', border: 'border-area-amber', dot: 'bg-area-amber' },
  rose: { block: 'border-area-rose bg-area-rose/12', border: 'border-area-rose', dot: 'bg-area-rose' },
  slate: { block: 'border-area-slate bg-area-slate/12', border: 'border-area-slate', dot: 'bg-area-slate' },
}
// Events of a calendar without an area stay neutral, so no colour suggests a wrong area.
const NEUTRAL: Style = { block: 'border-muted/70 bg-muted/10', border: 'border-muted/70', dot: 'bg-muted' }

/** Colour of an event: the colour of its calendar's area (CALENDAR_FEED_AREAS), else neutral. */
export function useEventStyle(): (event: CalendarEvent) => Style {
  const areas = useAreas().data
  const colors = new Map(areas?.map((area) => [area.slug, area.color]))
  return (event) => (event.area ? AREA_STYLES[colors.get(event.area) ?? ''] : undefined) ?? NEUTRAL
}
