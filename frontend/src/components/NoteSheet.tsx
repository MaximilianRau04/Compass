import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { toast } from 'sonner'

import { useCreateNote, useNote, useUpdateNote } from '../api/notes'
import { useAreas } from '../api/tasks'
import type { Note, NoteDraft } from '../api/types'
import { useI18n } from '../i18n/context'
import { button, overlay } from '../lib/ui'
import { Markdown } from './Markdown'

const field = 'w-full rounded-md border border-rule bg-paper px-3 py-2 text-[15px] focus:border-brass focus:outline-none'
const label = 'mb-1 block font-display text-xs font-semibold tracking-[0.12em] text-muted uppercase'

type Draft = { title: string; body: string; area_id: string; tags: string; pinned: boolean }

const toDraft = (note: Partial<Note>): Draft => ({
  title: note.title ?? '',
  body: note.body ?? '',
  area_id: note.area_id ? String(note.area_id) : '',
  tags: (note.tags ?? []).map((t) => `#${t}`).join(' '),
  pinned: note.pinned ?? false,
})

function changes(before: Draft, draft: Draft): NoteDraft {
  const out: NoteDraft = {}
  if (draft.title !== before.title) out.title = draft.title.trim()
  if (draft.body !== before.body) out.body = draft.body
  if (draft.area_id !== before.area_id) out.area_id = draft.area_id ? Number(draft.area_id) : null
  if (draft.tags !== before.tags) out.tags = draft.tags.split(/[\s,]+/).filter(Boolean)
  if (draft.pinned !== before.pinned) out.pinned = draft.pinned
  return out
}

/** Open an existing note (`noteId`), or a new one with `initial` values (`noteId` = "new"). */
export function NoteSheet({ noteId, initial, onClose }: { noteId: number | 'new' | null; initial?: Partial<Note>; onClose: () => void }) {
  const note = useNote(typeof noteId === 'number' ? noteId : null)
  const ready = noteId === 'new' || note.data
  return (
    <Dialog.Root open={noteId !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content
          className="fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto rounded-t-2xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[40rem] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
          aria-describedby={undefined}
        >
          {ready && noteId !== null && (
            <NoteForm key={noteId === 'new' ? 'new' : `${noteId}-${note.data?.updated_at}`} note={noteId === 'new' ? null : note.data!} initial={initial} onClose={onClose} />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function NoteForm({ note, initial, onClose }: { note: Note | null; initial?: Partial<Note>; onClose: () => void }) {
  const { t } = useI18n()
  const areas = useAreas()
  const create = useCreateNote()
  const update = useUpdateNote()
  const [before] = useState(() => toDraft(note ?? initial ?? {}))
  const [draft, setDraft] = useState(before)
  // Existing notes open for reading; new ones and empty ones for writing.
  const [editing, setEditing] = useState(!note || !note.body.trim())
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }))
  const pending = changes(before, draft)
  const dirty = note === null || Object.keys(pending).length > 0
  const busy = create.isPending || update.isPending

  const done = (message: string) => {
    toast.success(message)
    onClose()
  }
  const onError = (error: Error) => toast.error(error.message)

  const save = () => {
    if (!draft.title.trim()) return
    if (note === null) {
      const data = { ...changes(toDraft({}), draft), title: draft.title.trim(), task_id: initial?.task_id ?? null }
      create.mutate(data, { onSuccess: () => done(t('notes.created')), onError })
    } else if (Object.keys(pending).length > 0) {
      update.mutate({ id: note.id, data: pending }, { onSuccess: () => done(t('notes.saved')), onError })
    } else onClose()
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
      className="space-y-4"
    >
      <Dialog.Title className="sr-only">{note ? t('notes.edit') : t('notes.new')}</Dialog.Title>
      <textarea
        value={draft.title}
        onChange={(e) => set('title', e.target.value)}
        rows={1}
        required
        placeholder={t('notes.titlePlaceholder')}
        aria-label={t('notes.titleField')}
        className="w-full resize-none rounded-md bg-transparent font-display text-2xl leading-tight font-semibold placeholder:text-muted/60 focus-visible:outline-none"
      />

      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className={label}>{t('notes.body')}</span>
          <span className="flex gap-1 text-[12px]">
            {[false, true].map((edit) => (
              <button
                key={String(edit)}
                type="button"
                aria-pressed={editing === edit}
                onClick={() => setEditing(edit)}
                className={['rounded px-2 py-0.5', editing === edit ? 'bg-ink text-paper' : 'text-muted hover:text-ink'].join(' ')}
              >
                {edit ? t('notes.write') : t('notes.preview')}
              </button>
            ))}
          </span>
        </div>
        {editing ? (
          <textarea
            value={draft.body}
            onChange={(e) => set('body', e.target.value)}
            rows={12}
            placeholder={t('notes.bodyPlaceholder')}
            aria-label={t('notes.body')}
            className={`${field} font-mono text-label leading-relaxed`}
          />
        ) : draft.body.trim() ? (
          <Markdown text={draft.body} className="rounded-md border border-rule bg-paper px-3 py-2 text-[15px]" />
        ) : (
          <p className="rounded-md border border-dashed border-rule px-3 py-6 text-center text-sm text-muted">{t('notes.emptyBody')}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label} htmlFor="note-area">
            {t('sheet.area')}
          </label>
          <select id="note-area" value={draft.area_id} onChange={(e) => set('area_id', e.target.value)} className={field}>
            <option value="">{t('sheet.areaNone')}</option>
            {areas.data?.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={label} htmlFor="note-tags">
            {t('sheet.tags')}
          </label>
          <input id="note-tags" value={draft.tags} onChange={(e) => set('tags', e.target.value)} placeholder="#idee #kontext" className={field} />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={draft.pinned} onChange={(e) => set('pinned', e.target.checked)} className="accent-brass" />
        {t('notes.pin')}
      </label>

      <div className="flex items-center gap-2 pt-1">
        {note && (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              update.mutate({ id: note.id, data: { archived: !note.archived } }, { onSuccess: () => done(note.archived ? t('notes.restored') : t('notes.archived')), onError })
            }
            className="rounded-md px-3 py-2 text-sm text-muted hover:text-signal"
          >
            {note.archived ? t('notes.restore') : t('notes.archive')}
          </button>
        )}
        {note && note.source !== 'manual' && <span className="font-mono text-2xs text-muted">{t(`notes.source.${note.source}`)}</span>}
        <span className="flex-1" />
        <Dialog.Close className={button('quiet')}>{t('sheet.close')}</Dialog.Close>
        <button
          type="submit"
          disabled={!dirty || busy || !draft.title.trim()}
          className={`${button('primary')} font-display font-semibold tracking-wide uppercase`}
        >
          {t('sheet.save')}
        </button>
      </div>
    </form>
  )
}
