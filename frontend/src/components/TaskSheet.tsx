import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { useNotes } from '../api/notes'
import { useAreas, useTaskEvents, useUpdateTask } from '../api/tasks'
import type { Task, TaskPriority, TaskStatus, TaskUpdate } from '../api/types'
import { useI18n } from '../i18n/context'
import { recurrenceLabel } from '../lib/format'

const RECURRENCE_PRESETS = [
  '',
  'FREQ=DAILY',
  'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
  'FREQ=WEEKLY',
  'FREQ=WEEKLY;INTERVAL=2',
  'FREQ=MONTHLY',
  'FREQ=YEARLY',
]

const STATUSES: TaskStatus[] = ['open', 'in_progress', 'done', 'cancelled']
const PRIORITIES: TaskPriority[] = ['low', 'normal', 'high', 'urgent']
const EVENT_TYPES = ['created', 'updated', 'synced', 'completed', 'reopened', 'cancelled', 'status_changed'] as const

type Draft = {
  title: string
  notes: string
  area_id: string
  tags: string
  priority: TaskPriority
  status: TaskStatus
  due_date: string
  due_time: string
  scheduled_date: string
  recurrence: string
}

function toDraft(task: Task): Draft {
  return {
    title: task.title,
    notes: task.notes ?? '',
    area_id: task.area_id ? String(task.area_id) : '',
    tags: task.tags.map((t) => `#${t}`).join(' '),
    priority: task.priority,
    status: task.status,
    due_date: task.due_date ?? '',
    due_time: task.due_time?.slice(0, 5) ?? '',
    scheduled_date: task.scheduled_date ?? '',
    recurrence: task.recurrence ?? '',
  }
}

function changes(task: Task, draft: Draft): TaskUpdate {
  const before = toDraft(task)
  const out: TaskUpdate = {}
  const orNull = (v: string) => (v === '' ? null : v)
  if (draft.title !== before.title) out.title = draft.title.trim()
  if (draft.notes !== before.notes) out.notes = orNull(draft.notes)
  if (draft.area_id !== before.area_id) out.area_id = draft.area_id ? Number(draft.area_id) : null
  if (draft.tags !== before.tags) out.tags = draft.tags.split(/[\s,]+/).filter(Boolean)
  if (draft.priority !== before.priority) out.priority = draft.priority
  if (draft.status !== before.status) out.status = draft.status
  if (draft.due_date !== before.due_date) out.due_date = orNull(draft.due_date)
  if (draft.due_time !== before.due_time) out.due_time = orNull(draft.due_time)
  if (draft.scheduled_date !== before.scheduled_date) out.scheduled_date = orNull(draft.scheduled_date)
  if (draft.recurrence !== before.recurrence) out.recurrence = orNull(draft.recurrence)
  return out
}

const field = 'w-full rounded-md border border-rule bg-paper px-3 py-2 text-[15px] focus:border-brass focus:outline-none'
const label = 'mb-1 block font-display text-xs font-semibold tracking-[0.12em] text-muted uppercase'

export function TaskSheet({ task, onClose }: { task: Task | null; onClose: () => void }) {
  return (
    <Dialog.Root open={task !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]" />
        <Dialog.Content
          className="fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto rounded-t-2xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[34rem] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
          aria-describedby={undefined}
        >
          {task && <TaskForm key={task.id + task.updated_at} task={task} onClose={onClose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function TaskForm({ task, onClose }: { task: Task; onClose: () => void }) {
  const { t, locale } = useI18n()
  const [draft, setDraft] = useState<Draft>(() => toDraft(task))
  const areas = useAreas()
  const events = useTaskEvents(task.id)
  const notes = useNotes({ taskId: task.id })
  const update = useUpdateTask()
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }))
  const pending = changes(task, draft)
  const dirty = Object.keys(pending).length > 0

  const save = (data: TaskUpdate, message: string) =>
    update.mutate(
      { id: task.id, data },
      {
        onSuccess: () => {
          toast.success(message)
          onClose()
        },
        onError: (error) => toast.error(error.message),
      },
    )

  const recurrenceOptions = RECURRENCE_PRESETS.includes(draft.recurrence)
    ? RECURRENCE_PRESETS
    : [...RECURRENCE_PRESETS, draft.recurrence]

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (dirty) save(pending, t('sheet.saved'))
        else onClose()
      }}
      className="space-y-4"
    >
      <Dialog.Title className="sr-only">{t('sheet.title')}</Dialog.Title>
      <textarea
        value={draft.title}
        onChange={(e) => set('title', e.target.value)}
        rows={2}
        required
        aria-label={t('sheet.titleField')}
        className="w-full resize-none rounded-md bg-transparent font-display text-2xl leading-tight font-semibold focus-visible:outline-none"
      />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label} htmlFor="due_date">
            {t('sheet.due')}
          </label>
          <input id="due_date" type="date" value={draft.due_date} onChange={(e) => set('due_date', e.target.value)} className={field} />
        </div>
        <div>
          <label className={label} htmlFor="due_time">
            {t('sheet.time')}
          </label>
          <input id="due_time" type="time" value={draft.due_time} onChange={(e) => set('due_time', e.target.value)} className={field} />
        </div>
        <div>
          <label className={label} htmlFor="scheduled_date">
            {t('sheet.scheduled')}
          </label>
          <input
            id="scheduled_date"
            type="date"
            value={draft.scheduled_date}
            onChange={(e) => set('scheduled_date', e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label className={label} htmlFor="recurrence">
            {t('sheet.recurrence')}
          </label>
          <select id="recurrence" value={draft.recurrence} onChange={(e) => set('recurrence', e.target.value)} className={field}>
            {recurrenceOptions.map((rule) => (
              <option key={rule} value={rule}>
                {rule ? recurrenceLabel(rule, t, locale) : t('sheet.recurrenceNone')}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="area">
            {t('sheet.area')}
          </label>
          <select id="area" value={draft.area_id} onChange={(e) => set('area_id', e.target.value)} className={field}>
            <option value="">{t('sheet.areaNone')}</option>
            {areas.data?.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="priority">
            {t('sheet.priority')}
          </label>
          <select
            id="priority"
            value={draft.priority}
            onChange={(e) => set('priority', e.target.value as TaskPriority)}
            className={field}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {t(`priority.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="status">
            {t('sheet.status')}
          </label>
          <select id="status" value={draft.status} onChange={(e) => set('status', e.target.value as TaskStatus)} className={field}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="tags">
            {t('sheet.tags')}
          </label>
          <input id="tags" value={draft.tags} onChange={(e) => set('tags', e.target.value)} placeholder="#ki #paper" className={field} />
        </div>
      </div>

      <div>
        <label className={label} htmlFor="notes">
          {t('sheet.notes')}
        </label>
        <textarea id="notes" value={draft.notes} onChange={(e) => set('notes', e.target.value)} rows={3} className={field} />
      </div>

      {notes.data && notes.data.length > 0 && (
        <div>
          <span className={label}>{t('notes.title')}</span>
          <ul className="space-y-0.5 text-sm">
            {notes.data.map((note) => (
              <li key={note.id}>
                <Link to={`/notizen?id=${note.id}`} onClick={onClose} className="text-brass hover:underline">
                  {note.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        {task.status === 'cancelled' ? (
          <button
            type="button"
            onClick={() => save({ status: 'open' }, t('sheet.restored'))}
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink"
          >
            {t('sheet.restore')}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => save({ status: 'cancelled' }, t('sheet.discarded'))}
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-signal"
          >
            {t('sheet.discard')}
          </button>
        )}
        <span className="flex-1" />
        <Dialog.Close className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink">{t('sheet.close')}</Dialog.Close>
        <button
          type="submit"
          disabled={!dirty || update.isPending || !draft.title.trim()}
          className="rounded-md bg-brass px-4 py-2 font-display text-sm font-semibold tracking-wide text-brass-ink uppercase disabled:opacity-30"
        >
          {t('sheet.save')}
        </button>
      </div>

      {events.data && events.data.length > 0 && (
        <details className="border-t border-rule pt-3">
          <summary className={`${label} cursor-pointer`}>{t('sheet.history')}</summary>
          <ol className="mt-2 space-y-1 font-mono text-[11px] text-muted">
            {events.data.map((event) => (
              <li key={event.id} className="flex gap-3">
                <time className="shrink-0">
                  {new Date(event.created_at).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })}
                </time>
                <span>
                  {(EVENT_TYPES as readonly string[]).includes(event.type)
                    ? t(`event.${event.type as (typeof EVENT_TYPES)[number]}`)
                    : event.type}
                  {(event.type === 'updated' || event.type === 'synced') && `: ${Object.keys(event.payload).join(', ')}`}
                  {event.actor !== 'web' && ` (${event.actor})`}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </form>
  )
}
