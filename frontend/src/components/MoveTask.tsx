import { toast } from 'sonner'

import { useMoveTask, useUpdateTask } from '../api/tasks'
import type { Task } from '../api/types'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { nextWeekStart } from '../lib/calendar'
import { addDays, relativeDay } from '../lib/format'

export type MoveTarget = 'today' | 'tomorrow' | 'nextWeek'

const LABEL: Record<MoveTarget, MessageKey> = {
  today: 'move.today',
  tomorrow: 'move.tomorrow',
  nextWeek: 'move.nextWeek',
}

const dayOf = (target: MoveTarget, today: string) =>
  target === 'today' ? today : target === 'tomorrow' ? addDays(today, 1) : nextWeekStart(today)

/**
 * One tap puts a task on another day. The toast takes it back by restoring both dates.
 * `variant` is the look: small text links under a list entry, or pills in the task sheet.
 */
export function MoveTask({
  task,
  today,
  targets = ['today', 'tomorrow', 'nextWeek'],
  variant = 'links',
  disabled,
  onMoved,
}: {
  task: Task
  today: string
  targets?: MoveTarget[]
  variant?: 'links' | 'pills'
  disabled?: boolean
  onMoved?: () => void
}) {
  const { t, locale } = useI18n()
  const move = useMoveTask()
  const update = useUpdateTask()

  const onMove = (target: MoveTarget) => {
    const date = dayOf(target, today)
    const before = { due_date: task.due_date, scheduled_date: task.scheduled_date }
    move.mutate(
      { id: task.id, date },
      {
        onSuccess: () => {
          toast(t('move.done', { title: task.title, date: relativeDay(date, today, t, locale) }), {
            action: { label: t('task.undo'), onClick: () => update.mutate({ id: task.id, data: before }) },
          })
          onMoved?.()
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  const style =
    variant === 'pills'
      ? 'rounded-full border border-rule px-3 py-1 text-sm text-muted transition-colors hover:border-ink hover:text-ink disabled:pointer-events-none disabled:opacity-40'
      : // Small text, but a touch target of 32 px height through the padding.
        '-my-1.5 py-1.5 font-mono text-2xs text-brass hover:underline disabled:pointer-events-none disabled:opacity-40'
  return (
    <span role="group" aria-label={t('move.label', { title: task.title })} className={variant === 'pills' ? 'flex flex-wrap gap-1.5' : 'mt-1 flex gap-4'}>
      {targets.map((target) => (
        <button key={target} type="button" disabled={disabled || move.isPending} onClick={() => onMove(target)} className={style}>
          {variant === 'links' && '→ '}
          {t(LABEL[target])}
        </button>
      ))}
    </span>
  )
}
