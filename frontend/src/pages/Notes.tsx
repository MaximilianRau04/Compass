import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useNotes, useNoteTags } from '../api/notes'
import { useAreas, useTodayDate } from '../api/tasks'
import type { NoteListItem } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { NoteSheet } from '../components/NoteSheet'
import { useI18n } from '../i18n/context'
import { AREA_TEXT, localDay, pill, relativeDay } from '../lib/format'
import { button, pageTitle } from '../lib/ui'

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

function NoteRow({ note, today, onOpen }: { note: NoteListItem; today: string; onOpen: (id: number) => void }) {
  const { t, locale } = useI18n()
  return (
    <li>
      <button type="button" onClick={() => onOpen(note.id)} className="block w-full py-3 text-left hover:text-ink">
        <span className="flex items-baseline justify-between gap-3">
          <span className="min-w-0 truncate font-medium">
            {note.pinned && (
              <span className="mr-1.5 text-brass" aria-label={t('notes.pinned')}>
                ●
              </span>
            )}
            {note.title}
          </span>
          <span className="shrink-0 font-mono text-[11px] text-muted">{relativeDay(localDay(note.updated_at), today, t, locale)}</span>
        </span>
        {note.snippet && <span className="mt-0.5 line-clamp-2 block text-sm text-muted">{note.snippet}</span>}
        {(note.area || note.tags.length > 0) && (
          <span className="mt-1 flex flex-wrap gap-x-2 font-mono text-[11px] text-muted">
            {note.area && <span className={AREA_TEXT[note.area.color]}>{note.area.name}</span>}
            {note.tags.map((tag) => (
              <span key={tag}>#{tag}</span>
            ))}
          </span>
        )}
      </button>
    </li>
  )
}

export function NotesPage() {
  const { t } = useI18n()
  const today = useTodayDate()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [areaId, setAreaId] = useState<number | undefined>()
  const [tag, setTag] = useState<string | undefined>()
  const [archived, setArchived] = useState(false)
  const q = useDebounced(query.trim(), 250)
  const notes = useNotes({ q: q || undefined, areaId, tag, archived })
  const tags = useNoteTags()
  const areas = useAreas()

  const param = params.get('id')
  const open: number | 'new' | null = param === 'new' ? 'new' : param ? Number(param) : null
  const setOpen = (id: number | 'new' | null) => {
    const next = new URLSearchParams(params)
    if (id === null) next.delete('id')
    else next.set('id', id === 'new' ? 'new' : String(id))
    setParams(next, { replace: id === null })
  }

  const list = notes.data ?? []
  const pinned = list.filter((n) => n.pinned)
  const rest = list.filter((n) => !n.pinned)

  return (
    <>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h1 className={pageTitle}>{t('notes.title')}</h1>
        <button type="button" onClick={() => setOpen('new')} className={button('primary')}>
          {t('notes.new')}
        </button>
      </header>

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t('notes.search')}
        aria-label={t('notes.search')}
        className="mb-3 w-full rounded-md border border-rule bg-paper-raised px-3 py-2.5 focus:border-brass focus:outline-none"
      />

      <div className="mb-2 flex flex-wrap gap-1.5">
        <button type="button" className={pill(!areaId)} aria-pressed={!areaId} onClick={() => setAreaId(undefined)}>
          {t('mail.all')}
        </button>
        {areas.data?.map((area) => (
          <button key={area.id} type="button" className={pill(areaId === area.id)} aria-pressed={areaId === area.id} onClick={() => setAreaId(areaId === area.id ? undefined : area.id)}>
            {area.name}
          </button>
        ))}
        <button type="button" className={`${pill(archived)} ml-auto`} aria-pressed={archived} onClick={() => setArchived(!archived)}>
          {t('notes.archiveList')}
        </button>
      </div>
      {tags.data && tags.data.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[12px]">
          {tags.data.map(({ tag: name, count }) => (
            <button key={name} type="button" aria-pressed={tag === name} onClick={() => setTag(tag === name ? undefined : name)} className={tag === name ? 'text-brass' : 'text-muted hover:text-ink'}>
              #{name} <span className="text-[10px]">{count}</span>
            </button>
          ))}
        </div>
      )}

      {notes.error && <p className="text-signal">{t('notes.loadError', { message: notes.error.message })}</p>}
      {notes.isPending && <p className="font-mono text-sm text-muted">{t('common.loading')}</p>}
      {notes.data && list.length === 0 && <p className="max-w-md text-muted">{q || areaId || tag || archived ? t('notes.nothing') : t('notes.empty')}</p>}

      <div className="space-y-8">
        {pinned.length > 0 && (
          <section>
            <SectionLabel count={pinned.length}>{t('notes.pinnedList')}</SectionLabel>
            <ul className="divide-y divide-rule/60">
              {pinned.map((note) => (
                <NoteRow key={note.id} note={note} today={today} onOpen={setOpen} />
              ))}
            </ul>
          </section>
        )}
        {rest.length > 0 && (
          <section>
            <SectionLabel count={rest.length}>{archived ? t('notes.archiveList') : q ? t('notes.results') : t('notes.recent')}</SectionLabel>
            <ul className="divide-y divide-rule/60">
              {rest.map((note) => (
                <NoteRow key={note.id} note={note} today={today} onOpen={setOpen} />
              ))}
            </ul>
          </section>
        )}
        <p className="max-w-xl text-sm text-muted">{t('notes.hint')}</p>
      </div>

      <NoteSheet noteId={open} initial={open === 'new' && areaId ? { area_id: areaId } : undefined} onClose={() => setOpen(null)} />
    </>
  )
}
