import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { useAreas, useTasks, useTodayDate, useUpdateTask } from '../api/tasks'
import type { Task, TaskStatus } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { MoveTask } from '../components/MoveTask'
import { QuickAdd } from '../components/QuickAdd'
import { TaskItem } from '../components/TaskItem'
import { TaskSheet } from '../components/TaskSheet'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { AREA_BG, daysBetween, isLeftBehind, localDay, relativeDay } from '../lib/format'
import { pageTitle } from '../lib/ui'

type View = 'list' | 'board'

// The view lives in the URL (?view=board), so it survives reloads and can be linked.
const VIEW_PARAM: Record<View, string> = { list: 'list', board: 'board' }
type Scope = 'active' | 'done' | 'cancelled'

const SCOPES: Record<Scope, { label: MessageKey; status: TaskStatus[] }> = {
  active: { label: 'status.open', status: ['open', 'in_progress'] },
  done: { label: 'status.done', status: ['done'] },
  cancelled: { label: 'status.cancelled', status: ['cancelled'] },
}

const BOARD: { status: TaskStatus; next?: TaskStatus; nextLabel?: MessageKey }[] = [
  { status: 'open', next: 'in_progress', nextLabel: 'tasks.start' },
  { status: 'in_progress', next: 'done', nextLabel: 'tasks.finish' },
  { status: 'done' },
]

type Bucket = 'overdue' | 'today' | 'week' | 'later' | 'none'

function bucket(task: Task, today: string): Bucket {
  // Overdue is a deadline that has passed. A planned day that has passed brings the task along
  // to today, as on the Today page. Otherwise the earlier of the two decides.
  if (task.due_date && task.due_date < today) return 'overdue'
  const planned = task.scheduled_date && task.scheduled_date < today ? today : task.scheduled_date
  const date = [task.due_date, planned].filter(Boolean).sort()[0]
  if (!date) return 'none'
  const diff = daysBetween(today, date)
  if (diff === 0) return 'today'
  if (diff <= 7) return 'week'
  return 'later'
}
const BUCKET_ORDER: Bucket[] = ['overdue', 'today', 'week', 'later', 'none']

/** Done tasks by the day they were completed, the last one first. */
function byCompletionDay(tasks: Task[]): [string, Task[]][] {
  const at = (task: Task) => task.completed_at ?? task.updated_at
  const days = new Map<string, Task[]>()
  for (const task of [...tasks].sort((a, b) => at(b).localeCompare(at(a)))) {
    const day = localDay(at(task))
    days.set(day, [...(days.get(day) ?? []), task])
  }
  return [...days]
}

const toggle = (active: boolean) =>
  [
    'rounded-full border px-3 py-1 text-sm transition-colors',
    active ? 'border-ink bg-ink text-paper' : 'border-rule text-muted hover:border-ink hover:text-ink',
  ].join(' ')

export function TasksPage() {
  const { t, locale } = useI18n()
  const [params, setParams] = useSearchParams()
  const view = (Object.keys(VIEW_PARAM) as View[]).find((v) => VIEW_PARAM[v] === params.get('view')) ?? 'list'
  const setView = (next: View) => setParams(next === 'list' ? {} : { view: VIEW_PARAM[next] }, { replace: true })
  const [scope, setScope] = useState<Scope>('active')
  const [areaId, setAreaId] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Task | null>(null)

  const status = view === 'board' ? (['open', 'in_progress', 'done'] as TaskStatus[]) : SCOPES[scope].status
  const tasks = useTasks({ status, areaId, q: q.trim() || undefined })
  const areas = useAreas()
  const today = useTodayDate()
  const update = useUpdateTask()

  const list = tasks.data ?? []

  // The calendar used to be a view of this page; old links and bookmarks still lead there.
  if (params.get('ansicht') === 'kalender') return <Navigate to="/calendar" replace />

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h1 className={pageTitle}>{t('tasks.title')}</h1>
        <div className="flex gap-1" role="group" aria-label={t('tasks.view')}>
          <button type="button" className={toggle(view === 'list')} onClick={() => setView('list')}>
            {t('tasks.list')}
          </button>
          <button type="button" className={toggle(view === 'board')} onClick={() => setView('board')}>
            {t('tasks.board')}
          </button>
        </div>
      </header>

      <div className="fixed inset-x-0 bottom-[calc(3.6rem+env(safe-area-inset-bottom))] z-20 px-3 sm:static sm:mb-6 sm:px-0">
        <QuickAdd today={today} />
      </div>

      <div className="mb-6 space-y-3">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('tasks.search')}
          aria-label={t('tasks.searchLabel')}
          className="w-full rounded-md border border-rule bg-paper-raised px-3 py-2 focus:border-brass focus:outline-none"
        />
        <div className="flex flex-wrap gap-1.5">
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
        {view === 'list' && (
          <div className="flex gap-1.5">
            {(Object.keys(SCOPES) as Scope[]).map((s) => (
              <button key={s} type="button" className={toggle(scope === s)} onClick={() => setScope(s)}>
                {t(SCOPES[s].label)}
              </button>
            ))}
          </div>
        )}
      </div>

      {tasks.isPending && <p className="font-mono text-sm text-muted">{t('common.loading')}</p>}
      {tasks.error && <p className="text-signal">{t('tasks.loadError', { message: tasks.error.message })}</p>}
      {tasks.isSuccess && list.length === 0 && (
        <p className="text-muted">
          {q || areaId ? t('tasks.emptyFiltered') : t('tasks.empty')}
        </p>
      )}

      {view === 'list' && scope === 'active' && (
        <div className="space-y-8">
          {BUCKET_ORDER.map((name) => {
            const items = list.filter((t) => bucket(t, today) === name)
            if (items.length === 0) return null
            return (
              <section key={name}>
                <SectionLabel count={items.length} tone={name === 'overdue' ? 'signal' : undefined}>
                  {t(`bucket.${name}`)}
                </SectionLabel>
                <ul className="divide-y divide-rule/60">
                  {items.map((task) => (
                    <TaskItem key={task.id} task={task} today={today} onOpen={setOpen}>
                      {isLeftBehind(task, today) && <MoveTask task={task} today={today} targets={['today', 'tomorrow']} />}
                    </TaskItem>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}

      {view === 'list' && scope === 'done' && (
        <div className="space-y-8">
          {byCompletionDay(list).map(([day, items]) => (
            <section key={day}>
              <SectionLabel count={items.length}>{relativeDay(day, today, t, locale)}</SectionLabel>
              <ul className="divide-y divide-rule/60">
                {items.map((task) => (
                  <TaskItem key={task.id} task={task} today={today} onOpen={setOpen} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {view === 'list' && scope === 'cancelled' && (
        <ul className="divide-y divide-rule/60">
          {/* What was discarded last comes first. */}
          {[...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map((task) => (
            <TaskItem key={task.id} task={task} today={today} onOpen={setOpen} />
          ))}
        </ul>
      )}

      {view === 'board' && (
        <div className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0">
          {BOARD.map((column) => {
            const items = list.filter((t) => t.status === column.status)
            return (
              <section key={column.status} className="w-[82%] shrink-0 snap-start sm:w-auto">
                <SectionLabel count={items.length}>{t(`status.${column.status}`)}</SectionLabel>
                <ul className="divide-y divide-rule/60">
                  {items.map((task) => (
                    <TaskItem key={task.id} task={task} today={today} onOpen={setOpen}>
                      {column.next && (
                        <button
                          type="button"
                          onClick={() =>
                            update.mutate(
                              { id: task.id, data: { status: column.next } },
                              { onError: (error) => toast.error(error.message) },
                            )
                          }
                          className="mt-1 font-mono text-2xs text-brass hover:underline"
                        >
                          {column.nextLabel && t(column.nextLabel)} →
                        </button>
                      )}
                    </TaskItem>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}

      <TaskSheet task={open} onClose={() => setOpen(null)} />
    </>
  )
}
