/** The start screen: templates, the last workouts, a free workout or one entered afterwards. */

import { useState } from 'react'

import { useTodayDate } from '../../api/tasks'
import { fetchTemplate, useTemplates, useWorkoutNames } from '../../api/training'
import type { WorkoutTemplate } from '../../api/types'
import { SectionLabel } from '../../components/Layout'
import { TemplateEditor } from '../../components/TemplateEditor'
import { useI18n } from '../../i18n/context'
import { addDays, localDay, pill, relativeDay } from '../../lib/format'
import { button } from '../../lib/ui'
import { useUnits } from '../../lib/units'
import { type Draft, type DraftExercise, exerciseFrom, localIso, newId } from '../../lib/workout'
import { nowIso } from './hooks'
import { input } from './styles'

function TemplateCard({ template, onStart, onEdit, disabled }: { template: WorkoutTemplate; onStart: () => void; onEdit: () => void; disabled: boolean }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  return (
    <li className="flex rounded-lg border border-rule bg-paper-raised hover:border-ink">
      <button type="button" disabled={disabled} onClick={onStart} className="min-w-0 flex-1 px-3 py-3 text-left disabled:opacity-50">
        <span className="block truncate font-medium">{template.name}</span>
        <span className="block font-mono text-2xs text-muted">
          {t('log.exercisesN', { n: template.exercises.length })} · {template.last_at ? relativeDay(localDay(template.last_at), today, t, locale) : t('log.neverTrained')}
        </span>
      </button>
      <button type="button" onClick={onEdit} aria-label={t('log.edit', { name: template.name })} className="border-l border-rule px-3 text-muted hover:text-ink">
        ✎
      </button>
    </li>
  )
}

/** When a workout entered afterwards took place. */
export function PastFields({ day, time, minutes, onChange, max }: { day: string; time: string; minutes: string; onChange: (v: { day?: string; time?: string; minutes?: string }) => void; max: string }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 font-mono text-2xs text-muted">
        {t('log.pastDay')}
        <input type="date" value={day} max={max} onChange={(e) => onChange({ day: e.target.value })} className={input} />
      </label>
      <label className="flex flex-col gap-1 font-mono text-2xs text-muted">
        {t('log.pastTime')}
        <input type="time" value={time} onChange={(e) => onChange({ time: e.target.value })} className={input} />
      </label>
      <label className="flex flex-col gap-1 font-mono text-2xs text-muted">
        {t('log.pastMinutes')}
        <input value={minutes} inputMode="numeric" onChange={(e) => onChange({ minutes: e.target.value.replace(/\D/g, '').slice(0, 3) })} className={`${input} w-24`} />
      </label>
    </div>
  )
}

export function Start({ onStart }: { onStart: (d: Draft) => void }) {
  const { t, locale } = useI18n()
  const unit = useUnits().weightUnit
  const workouts = useWorkoutNames()
  const templates = useTemplates()
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<WorkoutTemplate | 'new' | null>(null)
  const today = useTodayDate()
  const [past, setPast] = useState(false)
  // 18:00 of the last evening that is over: today after 19:00, else yesterday.
  const [when, setWhen] = useState(() => ({ day: new Date().getHours() >= 19 ? today : addDays(today, -1), time: '18:00', minutes: '60' }))
  const [openedAt] = useState(() => Date.now())
  const pastStart = localIso(when.day, when.time)
  const pastValid = Boolean(when.day && when.time && Number(when.minutes) > 0) && new Date(pastStart).getTime() < openedAt

  const begin = async (workout: string) => {
    const title = workout.trim()
    if (!title) return
    setLoading(true)
    let exercises: DraftExercise[] = []
    let workoutName = title
    try {
      const template = await fetchTemplate(title)
      exercises = template.exercises.map((e) => exerciseFrom(e, unit))
      workoutName = template.workout_name
    } catch {
      // Offline: start empty, the exercises can be added by name.
    }
    const now = nowIso()
    onStart({
      client_id: newId(),
      workout_name: workoutName,
      started_at: past ? pastStart : now,
      ended_at: null,
      exercises,
      changed_at: now,
      synced_at: null,
      unit,
      ...(past ? { backfill: { minutes: Number(when.minutes) } } : {}),
    })
    setLoading(false)
  }
  const blocked = loading || (past && !pastValid)

  const planned = new Set((templates.data ?? []).map((x) => x.name.toLowerCase()))
  const recent = (workouts.data ?? []).filter((w) => !planned.has(w.name.toLowerCase()))

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div role="group" aria-label={t('log.mode')} className="flex gap-1.5">
          <button type="button" className={pill(!past)} aria-pressed={!past} onClick={() => setPast(false)}>
            {t('log.modeNow')}
          </button>
          <button type="button" className={pill(past)} aria-pressed={past} onClick={() => setPast(true)}>
            {t('log.modePast')}
          </button>
        </div>
        {past && (
          <div className="rounded-lg border border-rule bg-paper-raised p-3">
            <PastFields day={when.day} time={when.time} minutes={when.minutes} max={today} onChange={(v) => setWhen({ ...when, ...v })} />
            <p className={`mt-2 font-mono text-2xs ${pastValid ? 'text-muted' : 'text-signal'}`}>{pastValid ? t('log.pastHint') : t('log.pastInvalid')}</p>
          </div>
        )}
      </div>

      <section>
        <SectionLabel count={templates.data?.length || undefined}>{t('log.templates')}</SectionLabel>
        <p className="mt-1 font-mono text-2xs text-muted">{t('log.templatesHint')}</p>
        <ul className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-2 sm:grid-cols-2">
          {templates.data?.map((x) => (
            <TemplateCard key={x.id} template={x} disabled={blocked} onStart={() => void begin(x.name)} onEdit={() => setEditing(x)} />
          ))}
          <li>
            <button type="button" onClick={() => setEditing('new')} className="h-full min-h-14 w-full rounded-lg border border-dashed border-rule px-3 py-3 text-left text-muted hover:border-ink hover:text-ink">
              {t('log.build')}
            </button>
          </li>
        </ul>
      </section>

      {recent.length > 0 && (
        <section>
          <SectionLabel>{t('log.pick')}</SectionLabel>
          <ul className="mt-3 grid grid-cols-2 gap-2">
            {recent.map((w) => (
              <li key={w.name}>
                <button type="button" disabled={blocked} onClick={() => void begin(w.name)} className="w-full rounded-lg border border-rule bg-paper-raised px-3 py-3 text-left hover:border-ink disabled:opacity-50">
                  <span className="block truncate font-medium">{w.name}</span>
                  <span className="font-mono text-2xs text-muted">{relativeDay(localDay(w.last_at), today, t, locale)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <SectionLabel>{t('log.free')}</SectionLabel>
        {workouts.data?.length === 0 && templates.data?.length === 0 && <p className="mt-2 text-sm text-muted">{t('log.noWorkouts')}</p>}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void begin(name)
          }}
          className="mt-3 flex gap-2"
        >
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('log.newName')} aria-label={t('log.newName')} className="min-w-0 flex-1 rounded-md border border-rule bg-paper-raised px-3 py-2.5 focus:border-brass focus:outline-none" />
          <button type="submit" disabled={!name.trim() || blocked} className={button('primary')}>
            {t('log.start')}
          </button>
        </form>
      </section>

      <TemplateEditor open={editing !== null} template={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onStart={(n) => (blocked ? undefined : void begin(n))} />
    </div>
  )
}
