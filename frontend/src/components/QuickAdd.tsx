import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { useQuickAdd, useQuickAddPreview } from '../api/tasks'
import { useI18n } from '../i18n/context'
import { AREA_TEXT, recurrenceLabel, relativeDay, shortTime } from '../lib/format'

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

export function QuickAdd({
  today,
  initialText = '',
  autoFocus = false,
  onCreated,
}: {
  today: string
  initialText?: string
  autoFocus?: boolean
  onCreated?: () => void
}) {
  const { t, locale } = useI18n()
  const [text, setText] = useState(initialText)
  const input = useRef<HTMLInputElement>(null)
  const debounced = useDebounced(text, 250)
  const preview = useQuickAddPreview(debounced)
  const create = useQuickAdd()
  const p = text.trim() ? preview.data : undefined

  useEffect(() => {
    if (autoFocus) input.current?.focus()
  }, [autoFocus])

  // "n" anywhere focuses the input, like a keyboard shortcut in mail clients.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (event.key === 'n' && !event.metaKey && !event.ctrlKey && !target.closest('input, textarea, [role=dialog]')) {
        event.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!text.trim() || create.isPending) return
    create.mutate(text, {
      onSuccess: (task) => {
        setText('')
        toast.success(t('quick.created', { title: task.title }))
        onCreated?.()
      },
      onError: (error) => toast.error(error.message),
    })
  }

  const chips: { label: string; className?: string }[] = []
  if (p) {
    if (p.due_date) {
      const time = p.due_time ? ` ${shortTime(p.due_time)}` : ''
      chips.push({ label: `${t('task.due', { date: relativeDay(p.due_date, today, t, locale) })}${time}` })
    }
    if (p.scheduled_date) chips.push({ label: `@${relativeDay(p.scheduled_date, today, t, locale)}` })
    if (p.area) chips.push({ label: p.area.name, className: AREA_TEXT[p.area.color] })
    if (p.priority && p.priority !== 'normal') {
      chips.push({ label: t(`priority.${p.priority}`), className: p.priority === 'urgent' ? 'text-signal' : 'text-brass' })
    }
    if (p.recurrence) chips.push({ label: `↻ ${recurrenceLabel(p.recurrence, t, locale)}` })
    p.tags.forEach((tag) => chips.push({ label: `#${tag}` }))
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-rule bg-paper-raised shadow-[0_8px_24px_-12px_rgb(0_0_0/0.35)] transition-colors focus-within:border-brass">
      <label htmlFor="quick-add" className="sr-only">
        {t('quick.label')}
      </label>
      <div className="flex items-center gap-2 px-3">
        <span aria-hidden className="font-display text-xl font-semibold text-brass">
          +
        </span>
        <input
          id="quick-add"
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('quick.placeholder')}
          autoComplete="off"
          enterKeyHint="done"
          className="h-12 min-w-0 flex-1 bg-transparent text-[15px] placeholder:text-muted/70 focus-visible:outline-none"
        />
        <button
          type="submit"
          disabled={!text.trim() || create.isPending}
          className="rounded-md bg-brass px-3 py-1.5 font-display text-sm font-semibold tracking-wide text-brass-ink uppercase transition-opacity disabled:opacity-30"
        >
          {t('quick.submit')}
        </button>
      </div>
      {/* Only show the preview when something besides the title was recognized. */}
      {text.trim() && chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-rule px-3 py-2 font-mono text-[11px] text-muted">
          <span className="text-ink">{p?.title || '…'}</span>
          {chips.map((chip) => (
            <span key={chip.label} className={chip.className}>
              {chip.label}
            </span>
          ))}
        </div>
      )}
    </form>
  )
}
