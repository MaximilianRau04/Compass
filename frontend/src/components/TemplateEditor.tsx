import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { toast } from 'sonner'

import { useDeleteTemplate, useExercises, useSaveTemplate } from '../api/training'
import type { WorkoutTemplate, WorkoutTemplateItem } from '../api/types'
import { useI18n } from '../i18n/context'
import { button, overlay } from '../lib/ui'
import { newId, REST_DEFAULT, REST_OPTIONS, restLabel } from '../lib/workout'
import { ConfirmDialog } from './ConfirmDialog'

type Item = WorkoutTemplateItem & { key: string }

const field = 'w-full rounded-md border border-rule bg-paper px-3 py-2 focus:border-brass focus:outline-none'

function ItemRow({ item, index, count, onChange, onMove, onRemove }: { item: Item; index: number; count: number; onChange: (i: Item) => void; onMove: (by: -1 | 1) => void; onRemove: () => void }) {
  const { t } = useI18n()
  const step = 'grid h-8 w-8 place-items-center rounded-md border border-rule text-muted hover:border-ink hover:text-ink disabled:opacity-30'
  return (
    <li className="rounded-lg border border-rule bg-paper px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="w-5 shrink-0 font-mono text-[12px] text-muted">{index + 1}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
        <button type="button" disabled={index === 0} onClick={() => onMove(-1)} aria-label={t('log.moveUp', { name: item.name })} className={step}>
          ↑
        </button>
        <button type="button" disabled={index === count - 1} onClick={() => onMove(1)} aria-label={t('log.moveDown', { name: item.name })} className={step}>
          ↓
        </button>
        <button type="button" onClick={onRemove} aria-label={t('log.removeExercise', { name: item.name })} className={`${step} hover:border-signal hover:text-signal`}>
          ×
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 pl-7 text-sm">
        <span className="flex items-center gap-1.5">
          <button type="button" disabled={item.sets <= 1} onClick={() => onChange({ ...item, sets: item.sets - 1 })} aria-label={t('editor.fewer')} className={step}>
            −
          </button>
          <span className="w-16 text-center font-mono tabular-nums">{item.sets === 1 ? t('editor.oneSet') : t('editor.setsN', { n: item.sets })}</span>
          <button type="button" disabled={item.sets >= 20} onClick={() => onChange({ ...item, sets: item.sets + 1 })} aria-label={t('editor.more')} className={step}>
            +
          </button>
        </span>
        <label className="flex items-center gap-1.5 text-muted">
          {t('log.rest')}
          <select value={item.rest_seconds} onChange={(e) => onChange({ ...item, rest_seconds: Number(e.target.value) })} className="rounded-md border border-rule bg-paper-raised px-2 py-1 font-mono text-label text-ink">
            {REST_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {restLabel(s, t('log.restNone'))}
              </option>
            ))}
          </select>
        </label>
      </div>
    </li>
  )
}

function Editor({ template, onClose, onStart }: { template: WorkoutTemplate | null; onClose: () => void; onStart?: (name: string) => void }) {
  const { t } = useI18n()
  const exercises = useExercises()
  const save = useSaveTemplate()
  const remove = useDeleteTemplate()
  const [name, setName] = useState(template?.name ?? '')
  const [items, setItems] = useState<Item[]>(() => (template?.exercises ?? []).map((e) => ({ ...e, key: newId() })))
  const [adding, setAdding] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const add = () => {
    const title = adding.trim()
    if (!title) return
    const known = exercises.data?.find((e) => e.name.toLowerCase() === title.toLowerCase() || e.aliases.some((a) => a.toLowerCase() === title.toLowerCase()))
    const last = items[items.length - 1]
    setItems([...items, { key: newId(), exercise_id: known?.id ?? null, name: known?.name ?? title, sets: last?.sets ?? 3, rest_seconds: last?.rest_seconds ?? REST_DEFAULT }])
    setAdding('')
  }
  const move = (i: number, by: -1 | 1) => {
    const next = [...items]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    setItems(next)
  }
  const submit = (start: boolean) => {
    const data = { name: name.trim(), exercises: items.map(({ key: _key, ...rest }) => rest) }
    save.mutate(
      { id: template?.id, data },
      {
        onSuccess: (saved) => {
          toast(t('log.templateSaved', { name: saved.name }))
          onClose()
          if (start) onStart?.(saved.name)
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }
  const valid = name.trim().length > 0 && items.length > 0

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) submit(false)
      }}
    >
      <Dialog.Title className="font-display text-2xl font-semibold tracking-wide uppercase">{template ? t('editor.titleEdit') : t('editor.titleNew')}</Dialog.Title>
      <label className="block">
        <span className="mb-1 block font-mono text-2xs tracking-wider text-muted uppercase">{t('editor.name')}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('editor.namePlaceholder')} className={field} />
      </label>

      <div>
        <span className="mb-1 block font-mono text-2xs tracking-wider text-muted uppercase">{t('editor.exercises')}</span>
        {items.length === 0 && <p className="py-2 text-sm text-muted">{t('editor.empty')}</p>}
        <ul className="space-y-2">
          {items.map((item, i) => (
            <ItemRow
              key={item.key}
              item={item}
              index={i}
              count={items.length}
              onChange={(next) => setItems(items.map((x) => (x.key === item.key ? next : x)))}
              onMove={(by) => move(i, by)}
              onRemove={() => setItems(items.filter((x) => x.key !== item.key))}
            />
          ))}
        </ul>
        <div className="mt-2 flex gap-2">
          <input
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                add()
              }
            }}
            list="editor-exercises"
            placeholder={t('log.addExercise')}
            aria-label={t('log.addExercise')}
            className={`${field} min-w-0 flex-1`}
          />
          <datalist id="editor-exercises">
            {exercises.data?.map((e) => (
              <option key={e.id} value={e.name} />
            ))}
          </datalist>
          <button type="button" onClick={add} disabled={!adding.trim()} className={button('secondary')}>
            {t('log.add')}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-rule pt-4">
        {template && (
          <button type="button" onClick={() => setConfirmDelete(true)} className={button('danger')}>
            {t('editor.delete')}
          </button>
        )}
        <span className="flex-1" />
        <Dialog.Close className={button('quiet')}>{t('common.cancel')}</Dialog.Close>
        {onStart && (
          <button type="button" disabled={!valid || save.isPending} onClick={() => submit(true)} className={button('secondary')}>
            {t('editor.startNow')}
          </button>
        )}
        <button type="submit" disabled={!valid || save.isPending} className={button('primary')}>
          {t('editor.save')}
        </button>
      </div>

      {template && (
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={t('editor.deleteTitle')}
          description={t('editor.deleteText', { name: template.name })}
          confirm={t('editor.delete')}
          onConfirm={() =>
            remove.mutate(template.id, {
              onSuccess: () => {
                toast(t('editor.deleted'))
                onClose()
              },
              onError: (error) => toast.error(error.message),
            })
          }
        />
      )}
    </form>
  )
}

/** Build a workout: exercises in order, sets and rest per exercise. `template` null = new. */
export function TemplateEditor({ open, template, onClose, onStart }: { open: boolean; template: WorkoutTemplate | null; onClose: () => void; onStart?: (name: string) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto rounded-t-2xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[34rem] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
        >
          {/* Keyed so a different template starts from its own state. */}
          {open && <Editor key={template?.id ?? 'new'} template={template} onClose={onClose} onStart={onStart} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
