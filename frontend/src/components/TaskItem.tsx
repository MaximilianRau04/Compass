import { toast } from 'sonner'

import { useToggleDone } from '../api/tasks'
import type { Task } from '../api/types'
import { useI18n } from '../i18n/context'
import { AREA_BG, AREA_TEXT, isOverdue, recurrenceLabel, relativeDay, shortTime } from '../lib/format'

export function TaskItem({
  task,
  today,
  onOpen,
  children,
}: {
  task: Task
  today: string
  onOpen: (task: Task) => void
  children?: React.ReactNode
}) {
  const toggle = useToggleDone()
  const { t, locale } = useI18n()
  const sourceLabel = { ilias: 'ILIAS', feed: t('source.feed'), email: t('source.email'), claude: 'Claude', manual: null }[task.source]
  const done = task.status === 'done'
  const overdue = isOverdue(task, today)

  const onToggle = () =>
    toggle.mutate(task, {
      onSuccess: (updated) => {
        if (updated.status === 'done') {
          toast(t('task.completedToast', { title: task.title }), {
            action: { label: t('task.undo'), onClick: () => toggle.mutate(updated) },
          })
        }
      },
      onError: (error) => toast.error(error.message),
    })

  return (
    <li className="group flex items-start gap-3 py-2.5">
      <button
        type="button"
        onClick={onToggle}
        disabled={toggle.isPending}
        aria-label={t(done ? 'task.reopen' : 'task.complete', { title: task.title })}
        className={[
          'mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border-[1.5px] transition-colors',
          done
            ? 'border-sea bg-sea text-paper'
            : task.priority === 'urgent'
              ? 'border-signal hover:bg-signal/10'
              : task.priority === 'high'
                ? 'border-brass hover:bg-brass/10'
                : 'border-muted/60 hover:border-ink',
        ].join(' ')}
      >
        {done && (
          <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
            <path d="M2.5 6.2l2.3 2.3 4.7-5" fill="none" stroke="currentColor" strokeWidth="1.8" />
          </svg>
        )}
      </button>

      <div className="min-w-0 flex-1">
      <button type="button" onClick={() => onOpen(task)} className="w-full text-left">
        <span className={['block leading-snug', done ? 'text-muted line-through decoration-muted/50' : ''].join(' ')}>
          {task.title}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted">
          {task.area && (
            <span className={`inline-flex items-center gap-1.5 ${AREA_TEXT[task.area.color] ?? ''}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${AREA_BG[task.area.color] ?? 'bg-muted'}`} />
              {task.area.name}
            </span>
          )}
          {task.due_date && (
            <span className={overdue ? 'font-medium text-signal' : ''}>
              {t('task.due', { date: relativeDay(task.due_date, today, t, locale) })}
              {task.due_time && ` ${shortTime(task.due_time)}`}
            </span>
          )}
          {task.scheduled_date && task.scheduled_date !== today && (
            <span>@{relativeDay(task.scheduled_date, today, t, locale)}</span>
          )}
          {task.recurrence && <span>↻ {recurrenceLabel(task.recurrence, t, locale)}</span>}
          {task.tags.map((tag) => (
            <span key={tag}>#{tag}</span>
          ))}
          {sourceLabel && <span className="uppercase">{sourceLabel}</span>}
        </span>
      </button>
      {children}
      </div>
    </li>
  )
}
