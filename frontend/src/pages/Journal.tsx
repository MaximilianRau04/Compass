import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { type JournalDay, useJournal, useJournalDay, useSaveJournal } from '../api/journal'
import { SectionLabel } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { addDays, longDate, toIsoDate } from '../lib/format'
import { button, pageTitle } from '../lib/ui'

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
  if (parts.length === 0 && day.tasks_done.length === 0) return null
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
    </section>
  )
}

function Editor({ day, data }: { day: string; data: JournalDay }) {
  const { t } = useI18n()
  const save = useSaveJournal()
  const [mood, setMood] = useState(data.entry?.mood ?? null)
  const [energy, setEnergy] = useState(data.entry?.energy ?? null)
  const [text, setText] = useState(data.entry?.text ?? '')
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ day, data: { mood, energy, text } }, { onSuccess: () => toast(t('journal.saved')), onError: (error) => toast.error(error.message) })
      }}
    >
      <div className="flex flex-wrap gap-6">
        <Scale label="journal.mood" value={mood} onChange={setMood} />
        <Scale label="journal.energy" value={energy} onChange={setEnergy} />
      </div>
      <label className="block">
        <span className="mb-1 block font-mono text-2xs tracking-wider text-muted uppercase">{t('journal.text')}</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} placeholder={t('journal.placeholder')} className={field} />
      </label>
      <button type="submit" disabled={save.isPending} className={button('primary')}>
        {t('journal.save')}
      </button>
    </form>
  )
}

/** One page per day: mood, energy and a text, next to what the day held. */
export function JournalPage() {
  const { t, locale } = useI18n()
  const [params, setParams] = useSearchParams()
  const [today] = useState(() => toIsoDate(new Date()))
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
