import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { useCalendar, useIntegrations, useSyncCalendars } from '../api/calendar'
import { useAreas, useTasks, useTodayDate } from '../api/tasks'
import type { CalendarEvent, Task } from '../api/types'
import { CalendarAgenda, DayList } from '../components/CalendarAgenda'
import { EventSheet } from '../components/calendar/EventSheet'
import { MonthView } from '../components/calendar/MonthView'
import { WeekView } from '../components/calendar/WeekView'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { addMonths, isoWeek, monthGrid, weekStart } from '../lib/calendar'
import { AREA_BG, addDays, parseDate } from '../lib/format'
import { pageTitle } from '../lib/ui'

type View = 'week' | 'month' | 'agenda'

// View and day live in the URL (?view=month&date=2026-10-01), so reloads and links keep them.
const VIEW_PARAM: Record<View, string> = { week: 'week', month: 'month', agenda: 'agenda' }
const VIEW_LABEL: Record<View, MessageKey> = { week: 'cal.week', month: 'cal.month', agenda: 'cal.agenda' }
const AGENDA_DAYS = 14
const DATE = /^\d{4}-\d{2}-\d{2}$/

function useWide(): boolean {
  const query = '(min-width: 640px)'
  const [wide, setWide] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const media = window.matchMedia(query)
    const onChange = () => setWide(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return wide
}

const toggle = (active: boolean) =>
  [
    'rounded-full border px-3 py-1 text-sm transition-colors',
    active ? 'border-ink bg-ink text-paper' : 'border-rule text-muted hover:border-ink hover:text-ink',
  ].join(' ')

function Arrow({ flip }: { flip?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className={`h-4 w-4 ${flip ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function CalendarPage() {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const wide = useWide()
  const [params, setParams] = useSearchParams()
  const view = (Object.keys(VIEW_PARAM) as View[]).find((v) => VIEW_PARAM[v] === params.get('view')) ?? 'week'
  const dateParam = params.get('date')
  const anchor = dateParam && DATE.test(dateParam) ? dateParam : today
  const [selected, setSelected] = useState(anchor)
  const [areaId, setAreaId] = useState<number | null>(null)
  const [openTask, setOpenTask] = useState<Task | null>(null)
  const [openEvent, setOpenEvent] = useState<CalendarEvent | null>(null)

  const go = (next: { view?: View; date?: string }) => {
    const nextView = next.view ?? view
    const nextDate = next.date ?? anchor
    const out: Record<string, string> = {}
    if (nextView !== 'week') out.view = VIEW_PARAM[nextView]
    if (nextDate !== today) out.date = nextDate
    setParams(out, { replace: true })
    if (next.date) setSelected(next.date)
  }

  // Phones get three days at a time in the week view, starting at the chosen day.
  const weekDays = wide ? 7 : 3
  const days =
    view === 'week'
      ? Array.from({ length: weekDays }, (_, i) => addDays(wide ? weekStart(anchor) : anchor, i))
      : view === 'month'
        ? monthGrid(anchor)
        : Array.from({ length: AGENDA_DAYS }, (_, i) => addDays(anchor, i))
  const start = days[0]
  const end = days[days.length - 1]

  const step = (direction: 1 | -1) => {
    if (view === 'month') go({ date: addMonths(anchor, direction) })
    else go({ date: addDays(anchor, direction * (view === 'week' ? weekDays : AGENDA_DAYS)) })
  }
  // Swiping sideways on phones pages like the arrows do.
  const touch = useRef<{ x: number; y: number } | null>(null)
  const swipe = {
    onTouchStart: (e: React.TouchEvent) => {
      touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
    },
    onTouchEnd: (e: React.TouchEvent) => {
      const from = touch.current
      touch.current = null
      if (!from || view === 'agenda') return
      const dx = e.changedTouches[0].clientX - from.x
      const dy = e.changedTouches[0].clientY - from.y
      if (Math.abs(dx) > 60 && Math.abs(dx) > 2 * Math.abs(dy)) step(dx < 0 ? 1 : -1)
    },
  }
  const showsToday = view === 'month' ? anchor.slice(0, 7) === today.slice(0, 7) : start <= today && today <= end

  const events = useCalendar(start, end)
  const integrations = useIntegrations()
  const sync = useSyncCalendars()
  const calendarStates = integrations.data?.filter((state) => state.name.startsWith('calendar:')) ?? []
  const configError = integrations.data?.find((state) => state.name === 'calendar:config')?.last_error
  const tasks = useTasks({ status: ['open', 'in_progress'], areaId })
  const areas = useAreas()
  // The area filter applies to events too: those of calendars mapped to the area.
  const areaSlug = areas.data?.find((area) => area.id === areaId)?.slug
  const eventList = (events.data ?? []).filter((event) => areaId === null || event.area === areaSlug)
  const taskList = tasks.data ?? []

  const range = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' })
  const title =
    view === 'month'
      ? parseDate(anchor).toLocaleDateString(locale, { month: 'long', year: 'numeric' })
      : range.formatRange(parseDate(start), parseDate(end))

  return (
    <>
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <h1 className={pageTitle}>{t('cal.view')}</h1>
        <div className="flex gap-1" role="group" aria-label={t('tasks.view')}>
          {(Object.keys(VIEW_PARAM) as View[]).map((v) => (
            <button key={v} type="button" className={toggle(view === v)} onClick={() => go({ view: v })}>
              {t(VIEW_LABEL[v])}
            </button>
          ))}
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => step(-1)} aria-label={t('cal.prevPeriod')} className="grid h-8 w-8 place-items-center rounded-full border border-rule text-muted hover:border-ink hover:text-ink">
            <Arrow />
          </button>
          <button type="button" onClick={() => step(1)} aria-label={t('cal.nextPeriod')} className="grid h-8 w-8 place-items-center rounded-full border border-rule text-muted hover:border-ink hover:text-ink">
            <Arrow flip />
          </button>
          <p className="ml-1 font-display text-xl font-semibold tracking-wide sm:text-2xl" aria-live="polite">
            {title}
          </p>
          {view === 'week' && wide && <span className="font-mono text-xs text-muted">{t('cal.weekNumber', { n: isoWeek(start) })}</span>}
        </div>
        {!showsToday && (
          <button type="button" className={toggle(false)} onClick={() => go({ date: today })}>
            {t('cal.backToToday')}
          </button>
        )}
      </div>

      <div className="mb-5 flex flex-wrap gap-1.5">
        <button type="button" className={toggle(areaId === null)} onClick={() => setAreaId(null)}>
          {t('tasks.allAreas')}
        </button>
        {areas.data?.map((area) => (
          <button key={area.id} type="button" className={toggle(areaId === area.id)} onClick={() => setAreaId(area.id)}>
            <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${AREA_BG[area.color] ?? 'bg-muted'}`} />
            {area.name}
          </button>
        ))}
      </div>

      {(events.isPending || tasks.isPending) && <p className="mb-4 font-mono text-sm text-muted">{t('common.loading')}</p>}
      {events.error && <p className="mb-4 text-signal">{t('cal.loadError', { message: events.error.message })}</p>}
      {tasks.error && <p className="mb-4 text-signal">{t('tasks.loadError', { message: tasks.error.message })}</p>}

      <div {...swipe}>
        {view === 'week' && (
          <>
            <WeekView
              days={days}
              events={eventList}
              tasks={taskList}
              today={today}
              selected={selected}
              onSelect={(day) => setSelected(day === selected ? '' : day)}
              onOpenTask={setOpenTask}
              onOpenEvent={setOpenEvent}
            />
            {days.includes(selected) && (
              <div className="mt-6">
                <DayList day={selected} today={today} events={eventList} tasks={taskList} onOpen={setOpenTask} onOpenEvent={setOpenEvent} />
              </div>
            )}
          </>
        )}

        {view === 'month' && (
          <>
            <MonthView
              anchor={anchor}
              selected={selected}
              events={eventList}
              tasks={taskList}
              today={today}
              onSelect={setSelected}
              onOpenTask={setOpenTask}
              onOpenEvent={setOpenEvent}
            />
            {days.includes(selected) && (
              <div className="mt-6">
                <DayList day={selected} today={today} events={eventList} tasks={taskList} onOpen={setOpenTask} onOpenEvent={setOpenEvent} />
              </div>
            )}
          </>
        )}
      </div>

      {view === 'agenda' && events.isSuccess && (
        <CalendarAgenda days={days} events={eventList} tasks={taskList} today={today} onOpen={setOpenTask} onOpenEvent={setOpenEvent} />
      )}

      <section className="mt-10 border-t border-rule pt-4" aria-label={t('cal.sources')}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-lg font-semibold">{t('cal.sources')}</h2>
          <button
            type="button"
            disabled={sync.isPending}
            className="text-sm text-brass hover:underline disabled:opacity-50"
            onClick={() => sync.mutate(undefined, {
              onSuccess: (result) => {
                const failed = Object.values(result).filter((value) => typeof value === 'string').length
                toast(failed ? t('cal.syncPartial', { n: failed }) : t('cal.synced'))
              },
              onError: (error) => toast.error(error.message),
            })}
          >
            {sync.isPending ? t('cal.syncing') : t('cal.sync')}
          </button>
        </div>
        {integrations.isPending && <p className="mt-2 text-sm text-muted">{t('common.loading')}</p>}
        {integrations.error && <p className="mt-2 text-sm text-signal">{t('cal.statusError', { message: integrations.error.message })}</p>}
        {integrations.isSuccess && (
          <div className="mt-2 space-y-2 text-sm">
            {configError && <p className="text-signal">{t('cal.configError', { message: configError })}</p>}
            {calendarStates.filter((state) => state.name !== 'calendar:config').length === 0 && !configError && (
              <p className="text-muted">{t('cal.noFeeds')}</p>
            )}
            {calendarStates.filter((state) => state.name !== 'calendar:config').map((state) => (
              <div key={state.name} className="flex flex-wrap gap-x-2 gap-y-0.5 border-b border-rule/60 pb-2 last:border-0">
                <span className="min-w-0 break-words font-medium text-ink">{state.name.slice('calendar:'.length)}</span>
                <span className="min-w-0 break-words text-muted">
                  {state.last_success_at
                    ? t('cal.sourceLast', { time: new Date(state.last_success_at).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) })
                    : t('cal.sourceNever')}
                </span>
                {state.last_error && <span className="w-full min-w-0 break-words text-signal">{t('cal.sourceError', { message: state.last_error })}</span>}
              </div>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">{t('cal.sourceHint')}</p>
      </section>

      <TaskSheet task={openTask} onClose={() => setOpenTask(null)} />
      <EventSheet event={openEvent} onClose={() => setOpenEvent(null)} />
    </>
  )
}
