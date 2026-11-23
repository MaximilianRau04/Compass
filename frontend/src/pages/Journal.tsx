import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { type JournalDay, useJournal, useJournalDay, useSaveJournal } from '../api/journal'
import { SectionLabel } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { addDays, longDate, toIsoDate } from '../lib/format'
import { clearJournalDraft, loadJournalDraft, saveJournalDraft } from '../lib/journalDraft'
import { button, pageTitle } from '../lib/ui'
import { useDeviceNow } from '../lib/useClock'

const field = 'w-full rounded-md border border-rule bg-paper px-3 py-2 focus:border-brass focus:outline-none'

/** 1 to 5; tapping the chosen value again clears it. */
function Scale({ label, value, onChange }: { label: MessageKey; value: number | null; onChange: (n: number | null) => void }) {
  const { t } = useI18n()
  return (
    <fieldset>
      <legend className="mb-1 block font-mono text-2xs tracking-wider text-muted uppercase">{t(label)}</legend>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={value === n}
            aria-label={t('journal.scale', { n })}
            onClick={() => onChange(value === n ? null : n)}
            className={`grid h-9 w-9 place-items-center rounded-md border font-mono text-label ${value === n ? 'border-brass bg-brass/15 text-ink' : 'border-rule text-muted hover:border-ink hover:text-ink'}`}
          >
            {n}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function Numbers({ day }: { day: JournalDay }) {
  const { t, locale } = useI18n()
  const parts = [
    day.asleep_minutes != null && t('journal.sleep', { h: (day.asleep_minutes / 60).toLocaleString(locale, { maximumFractionDigits: 1 }) }),
    day.steps != null && t('journal.steps', { n: day.steps.toLocaleString(locale) }),
    day.resting_hr != null && t('journal.resting', { bpm: day.resting_hr }),
    day.kcal != null && t('journal.kcal', { kcal: day.kcal, protein: day.protein_g ?? 0 }),
    day.weight_kg != null && t('journal.weight', { kg: day.weight_kg.toLocaleString(locale) }),
    ...day.training,
  ].filter(Boolean) as string[]
  return (
    <section>
      <SectionLabel>{t('journal.day')}</SectionLabel>
      {parts.length > 0 && <p className="mt-1 font-mono text-sm text-muted">{parts.join(' · ')}</p>}
      {day.tasks_done.length > 0 && (
        <>
          <p className="mt-3 font-mono text-2xs tracking-wider text-muted uppercase">{t('journal.tasksDone')}</p>
          <ul className="mt-1 list-disc pl-5">
            {day.tasks_done.map((title, i) => (
              <li key={i}>{title}</li>
            ))}
          </ul>
        </>
      )}
      <div className="mt-3 flex items-baseline justify-between gap-2">
        <p className="font-mono text-2xs tracking-wider text-muted uppercase">{t('journal.notes')}</p>
        <Link to="/notes?id=new" className="font-mono text-2xs text-brass hover:underline">
          + {t('notes.new')}
        </Link>
      </div>
      {day.notes.length > 0 && (
        <ul className="mt-1 space-y-1">
          {day.notes.map((note) => (
            <li key={note.id}>
              <Link to={`/notes?id=${note.id}`} className="text-brass hover:underline">
                {note.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Editor({ day, data }: { day: string; data: JournalDay }) {
  const { t } = useI18n()
  const save = useSaveJournal()
  const [initial] = useState(() => loadJournalDraft(day, data.entry))
  const [mood, setMood] = useState(initial.mood)
  const [energy, setEnergy] = useState(initial.energy)
  const [text, setText] = useState(initial.text)
  const [saved, setSaved] = useState(false)
  const [draftStored, setDraftStored] = useState(true)
  const isDirty = (m: number | null, en: number | null, tx: string) =>
    m !== (data.entry?.mood ?? null) || en !== (data.entry?.energy ?? null) || tx !== (data.entry?.text ?? '')
  const dirty = isDirty(mood, energy, text)
  const persist = (m: number | null, en: number | null, tx: string) => {
    if (saved) return
    if (isDirty(m, en, tx)) setDraftStored(saveJournalDraft(day, { mood: m, energy: en, text: tx }, data.entry?.updated_at ?? null))
    else {
      clearJournalDraft(day)
      setDraftStored(true)
    }
  }
  useEffect(() => {
    if (!dirty || draftStored || saved) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, draftStored, saved])
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ day, data: { mood, energy, text } }, {
          onSuccess: () => {
            setSaved(true)
            clearJournalDraft(day)
            toast(t('journal.saved'))
          },
          onError: (error) => toast.error(error.message),
        })
      }}
    >
      <div className="flex flex-wrap gap-6">
        <Scale label="journal.mood" value={mood} onChange={(v) => { setMood(v); persist(v, energy, text) }} />
        <Scale label="journal.energy" value={energy} onChange={(v) => { setEnergy(v); persist(mood, v, text) }} />
      </div>
      <label className="block">
        <span className="mb-1 block font-mono text-2xs tracking-wider text-muted uppercase">{t('journal.text')}</span>
        <textarea value={text} onChange={(e) => { const v = e.target.value; setText(v); persist(mood, energy, v) }} rows={6} maxLength={20000} placeholder={t('journal.placeholder')} className={field} />
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" disabled={save.isPending || saved || !dirty} className={button('primary')}>
          {t('journal.save')}
        </button>
        {dirty && !saved && <span className="text-label text-muted">{t(draftStored ? 'journal.draftSaved' : 'journal.draftUnavailable')}</span>}
      </div>
    </form>
  )
}

/** One page per day: mood, energy and a text, next to what the day held. */
export function JournalPage() {
  const { t, locale } = useI18n()
  const [params, setParams] = useSearchParams()
  const today = toIsoDate(useDeviceNow())
  const day = params.get('day') ?? today
  const data = useJournalDay(day)
  const recent = useJournal(30)
  const { weekday, date } = longDate(day, locale)
  const go = (to: string) => setParams(to === today ? {} : { day: to })

  return (
    <>
      <header className="mb-6 flex items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-muted">{date}</p>
          <h1 className={pageTitle}>{weekday}</h1>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => go(addDays(day, -1))} className={button('secondary')} aria-label={t('journal.prev')}>
            ←
          </button>
          <button type="button" disabled={day >= today} onClick={() => go(addDays(day, 1))} className={button('secondary')} aria-label={t('journal.next')}>
            →
          </button>
        </div>
      </header>
      <p className="mb-6 max-w-2xl text-sm leading-relaxed text-muted">{t('journal.intro')} <Link to="/correlations" className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink">{t('journal.correlationsLink')} →</Link></p>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="space-y-8">
          {data.isPending && <p className="font-mono text-sm text-muted">{t('common.loading')}</p>}
          {/* Keyed by the day and the last save, so another day or an entry written by the assistant starts fresh. */}
          {data.data && <Editor key={`${day}:${data.data.entry?.updated_at ?? ''}`} day={day} data={data.data} />}
          {data.data && <Numbers day={data.data} />}
          {data.data && data.data.briefs.length > 0 && (
            <section className="space-y-2">
              <SectionLabel>{t('journal.briefs')}</SectionLabel>
              {data.data.briefs.map((b) => (
                <details key={b.kind} className="rounded-md border border-rule px-4 py-3">
                  <summary className="cursor-pointer list-none font-display text-label font-semibold tracking-[0.18em] text-muted uppercase">{b.title ?? b.kind}</summary>
                  <Markdown text={b.body} className="mt-2" />
                </details>
              ))}
            </section>
          )}
        </div>

        <section>
          <SectionLabel>{t('journal.recent')}</SectionLabel>
          {recent.data?.length === 0 && <p className="py-2 text-sm text-muted">{t('journal.empty')}</p>}
          <ul className="divide-y divide-rule/60">
            {recent.data?.map((e) => (
              <li key={e.local_date}>
                <button type="button" onClick={() => go(e.local_date)} className={`block w-full py-2 text-left hover:text-brass ${e.local_date === day ? 'text-brass' : ''}`}>
                  <span className="font-mono text-2xs text-muted">
                    {e.local_date} · {e.mood ?? '–'}/{e.energy ?? '–'}
                  </span>
                  {e.text && <span className="block truncate text-sm">{e.text}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  )
}
