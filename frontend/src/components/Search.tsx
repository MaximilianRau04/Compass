import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { SEARCH_MIN, useSearch } from '../api/search'
import { useTodayDate } from '../api/tasks'
import type { Task } from '../api/types'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { eventTime, localDay, relativeDay, shortTime } from '../lib/format'
import { overlay } from '../lib/ui'
import { TaskSheet } from './TaskSheet'

interface Hit {
  key: string
  group: MessageKey
  title: string
  detail?: string
  /** Done and discarded tasks are shown struck through. */
  closed?: boolean
  run: () => void
}

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

/**
 * The search over everything: pages by name, and tasks, notes, journal entries, events and mails
 * by their text.
 * Opened with Ctrl/Cmd+K or "/" and from the navigation. Arrow keys and Enter pick a hit.
 */
export function Search({
  open,
  onOpenChange,
  pages,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  pages: { to: string; label: MessageKey }[]
}) {
  const [task, setTask] = useState<Task | null>(null)
  return (
    <>
      <Dialog.Root open={open} onOpenChange={onOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className={overlay} />
          <Dialog.Content
            aria-describedby={undefined}
            className="fixed inset-x-3 top-[max(0.75rem,env(safe-area-inset-top))] z-50 flex max-h-[min(34rem,calc(100dvh-1.5rem))] flex-col overflow-hidden rounded-2xl border border-rule bg-paper-raised shadow-xl sm:inset-x-auto sm:top-[12vh] sm:left-1/2 sm:w-[36rem] sm:-translate-x-1/2"
          >
            {/* Mounted only while open, so every opening starts with an empty field. */}
            <SearchBody pages={pages} onClose={() => onOpenChange(false)} onOpenTask={setTask} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <TaskSheet task={task} onClose={() => setTask(null)} />
    </>
  )
}

function SearchBody({
  pages,
  onClose,
  onOpenTask,
}: {
  pages: { to: string; label: MessageKey }[]
  onClose: () => void
  onOpenTask: (task: Task) => void
}) {
  const { t, locale } = useI18n()
  const navigate = useNavigate()
  const today = useTodayDate()
  const [text, setText] = useState('')
  const [picked, setPicked] = useState(0)
  const q = useDebounced(text.trim(), 200)
  const search = useSearch(q)
  const typed = text.trim().toLowerCase()
  const ready = q.length >= SEARCH_MIN && typed.length >= SEARCH_MIN
  const found = ready ? search.data : undefined

  const go = (to: string) => () => {
    onClose()
    void navigate(to)
  }
  const hits: Hit[] = [
    ...pages
      .filter((page) => typed && t(page.label).toLowerCase().includes(typed))
      .map((page) => ({ key: `page${page.to}`, group: 'search.pages' as const, title: t(page.label), run: go(page.to) })),
    ...(found?.tasks ?? []).map((task) => ({
      key: `task${task.id}`,
      group: 'nav.tasks' as const,
      title: task.title,
      detail: [
        task.status === 'done' || task.status === 'cancelled' ? t(`status.${task.status}`) : null,
        task.area?.name,
        task.due_date &&
          `${t('task.due', { date: relativeDay(task.due_date, today, t, locale) })}${task.due_time ? ` ${shortTime(task.due_time)}` : ''}`,
        !task.due_date && task.scheduled_date && `@${relativeDay(task.scheduled_date, today, t, locale)}`,
      ]
        .filter(Boolean)
        .join(' · '),
      closed: task.status === 'done' || task.status === 'cancelled',
      run: () => {
        onClose()
        onOpenTask(task)
      },
    })),
    ...(found?.notes ?? []).map((note) => ({
      key: `note${note.id}`,
      group: 'nav.notes' as const,
      title: note.title,
      detail: note.snippet,
      run: go(`/notes?id=${note.id}`),
    })),
    ...(found?.journal ?? []).map((entry) => ({
      key: `journal${entry.local_date}`,
      group: 'nav.journal' as const,
      title: relativeDay(entry.local_date, today, t, locale),
      detail: entry.snippet,
      run: go(`/journal?day=${entry.local_date}`),
    })),
    ...(found?.events ?? []).map((event) => {
      const day = localDay(event.starts_at)
      return {
        key: `event${event.id}`,
        group: 'nav.calendar' as const,
        title: event.title,
        detail: [`${relativeDay(day, today, t, locale)}, ${eventTime(event, t, locale)}`, event.location].filter(Boolean).join(' · '),
        run: go(`/calendar?date=${day}`),
      }
    }),
    ...(found?.mails ?? []).map((mail) => ({
      key: `mail${mail.id}`,
      group: 'nav.mail' as const,
      title: mail.subject,
      detail: [mail.from_name ?? mail.from_addr, relativeDay(localDay(mail.received_at), today, t, locale)].join(' · '),
      run: go(`/mail?id=${mail.id}`),
    })),
  ]
  const active = Math.min(picked, hits.length - 1)

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (hits.length === 0) return
      const next = (active + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length
      setPicked(next)
      // The first hit takes its heading along, which scrollIntoView would leave above the edge.
      if (next === 0) document.getElementById('search-hits')?.scrollTo({ top: 0 })
      else document.getElementById(`search-hit-${next}`)?.scrollIntoView({ block: 'nearest' })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      hits[active]?.run()
    }
  }

  return (
    <>
      <Dialog.Title className="sr-only">{t('search.title')}</Dialog.Title>
      <div className="flex items-center gap-3 border-b border-rule px-4">
        <SearchIcon className="h-5 w-5 shrink-0 text-muted" />
        {/* Without the browser's own clear button: closing does the same, every opening starts empty. */}
        <input
          type="search"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setPicked(0)
          }}
          onKeyDown={onKeyDown}
          autoFocus
          enterKeyHint="search"
          placeholder={t('search.placeholder')}
          aria-label={t('search.title')}
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls="search-hits"
          aria-activedescendant={hits.length > 0 ? `search-hit-${active}` : undefined}
          className="min-w-0 flex-1 bg-transparent py-3.5 text-lg focus:outline-none [&::-webkit-search-cancel-button]:hidden"
        />
        {/* A key to press where there is a keyboard, a word to tap on the phone. */}
        <Dialog.Close className="-mr-2 shrink-0 px-2 py-2 text-sm text-muted hover:text-ink sm:hidden">{t('sheet.close')}</Dialog.Close>
        <Dialog.Close
          aria-label={t('sheet.close')}
          className="hidden shrink-0 rounded border border-rule px-1.5 py-0.5 font-mono text-2xs text-muted hover:border-ink hover:text-ink sm:block"
        >
          Esc
        </Dialog.Close>
      </div>

      <ul id="search-hits" role="listbox" aria-label={t('search.results')} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2 empty:hidden">
        {hits.map((hit, i) => (
          <li key={hit.key} role="presentation">
            {(i === 0 || hits[i - 1].group !== hit.group) && (
              <p className={`px-2 pb-1 font-display text-label font-semibold tracking-[0.18em] text-muted uppercase ${i === 0 ? 'pt-1' : 'pt-3'}`}>
                {t(hit.group)}
              </p>
            )}
            <button
              type="button"
              id={`search-hit-${i}`}
              role="option"
              aria-selected={i === active}
              tabIndex={-1}
              onClick={hit.run}
              onPointerMove={() => i !== active && setPicked(i)}
              className={['block w-full rounded-md px-2 py-2 text-left', i === active ? 'bg-paper' : ''].join(' ')}
            >
              <span className={['block truncate leading-snug', hit.closed ? 'text-muted line-through' : ''].join(' ')}>{hit.title}</span>
              {hit.detail && <span className="block truncate font-mono text-2xs text-muted">{hit.detail}</span>}
            </button>
          </li>
        ))}
      </ul>

      {hits.length === 0 && (
        <p className="px-4 py-4 text-sm text-muted">
          {search.error
            ? search.error.message
            : typed.length < SEARCH_MIN
              ? t('search.hint')
              : !ready || search.isFetching
                ? t('common.loading')
                : t('search.empty', { query: text.trim() })}
        </p>
      )}
    </>
  )
}

export function SearchIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM20 20l-4.6-4.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
