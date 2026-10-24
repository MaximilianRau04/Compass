import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { useTodayDate } from '../api/tasks'
import { fetchExerciseTarget, fetchTemplate, useExercises, useWorkoutNames } from '../api/training'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import { decimal, localDay, pill, relativeDay } from '../lib/format'
import { type Draft, type DraftExercise, type DraftSet, discardDraft, exerciseFrom, loadDraft, newId, sendDraft, storeDraft } from '../lib/workout'

type Sync = 'saved' | 'saving' | 'pending' | 'offline'

const nowIso = () => new Date().toISOString()

const RIR_OPTIONS = ['', '0', '1', '2', '3', '4']
const field = 'w-full min-w-0 rounded-md border border-rule bg-paper px-2 py-2 text-center font-mono text-[15px] tabular-nums focus:border-brass focus:outline-none'

/** Keeps the draft in localStorage and on the server; retries until the server has the last change. */
function useDraft() {
  const [draft, setDraftState] = useState<Draft | null>(() => loadDraft())
  const [sync, setSync] = useState<Sync>('saved')
  const latest = useRef(draft)
  // Declared before the effects that send, so they always see the current draft.
  useEffect(() => {
    latest.current = draft
  }, [draft])

  const setDraft = useCallback((update: (d: Draft) => Draft) => {
    setDraftState((d) => {
      if (!d) return d
      const next = { ...update(d), changed_at: nowIso() }
      storeDraft(next)
      return next
    })
  }, [])

  const push = useCallback(async () => {
    const d = latest.current
    if (!d || (d.synced_at && d.synced_at >= d.changed_at)) return true
    const hasSets = d.exercises.some((e) => e.sets.some((s) => s.done))
    if (!hasSets && !d.synced_at) return true // nothing worth a session on the server yet
    setSync('saving')
    try {
      await sendDraft(d)
      setDraftState((current) => {
        if (!current || current.client_id !== d.client_id) return current
        const next = { ...current, synced_at: d.changed_at }
        storeDraft(next)
        return next
      })
      setSync('saved')
      return true
    } catch {
      setSync(navigator.onLine ? 'pending' : 'offline')
      return false
    }
  }, [])

  // Send a second after the last change, and keep trying while something is unsent.
  useEffect(() => {
    if (!draft || (draft.synced_at && draft.synced_at >= draft.changed_at)) return
    const id = setTimeout(() => void push(), 1000)
    return () => clearTimeout(id)
  }, [draft, push])
  useEffect(() => {
    const retry = () => void push()
    window.addEventListener('online', retry)
    const id = setInterval(retry, 20_000)
    return () => {
      window.removeEventListener('online', retry)
      clearInterval(id)
    }
  }, [push])

  const start = (d: Draft) => {
    storeDraft(d)
    setDraftState(d)
  }
  const clear = () => {
    storeDraft(null)
    setDraftState(null)
  }
  return { draft, setDraft, sync, push, start, clear }
}

function Start({ onStart }: { onStart: (d: Draft) => void }) {
  const { t, locale } = useI18n()
  const workouts = useWorkoutNames()
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const today = useTodayDate()

  const begin = async (workout: string) => {
    const title = workout.trim()
    if (!title) return
    setLoading(true)
    let exercises: DraftExercise[] = []
    try {
      exercises = (await fetchTemplate(title)).exercises.map(exerciseFrom)
    } catch {
      // Offline: start empty, the exercises can be added by name.
    }
    const now = nowIso()
    onStart({ client_id: newId(), workout_name: title, started_at: now, ended_at: null, exercises, changed_at: now, synced_at: null })
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <section>
        <SectionLabel>{t('log.pick')}</SectionLabel>
        <ul className="mt-3 grid grid-cols-2 gap-2">
          {workouts.data?.map((w) => (
            <li key={w.name}>
              <button type="button" disabled={loading} onClick={() => void begin(w.name)} className="w-full rounded-lg border border-rule bg-paper-raised px-3 py-3 text-left hover:border-ink disabled:opacity-50">
                <span className="block font-medium">{w.name}</span>
                <span className="font-mono text-[11px] text-muted">{relativeDay(localDay(w.last_at), today, t, locale)}</span>
              </button>
            </li>
          ))}
        </ul>
        {workouts.data?.length === 0 && <p className="mt-2 text-sm text-muted">{t('log.noWorkouts')}</p>}
      </section>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void begin(name)
        }}
        className="flex gap-2"
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('log.newName')} aria-label={t('log.newName')} className="min-w-0 flex-1 rounded-md border border-rule bg-paper-raised px-3 py-2.5 focus:border-brass focus:outline-none" />
        <button type="submit" disabled={!name.trim() || loading} className="rounded-md bg-brass px-4 py-2.5 font-medium text-brass-ink disabled:opacity-40">
          {t('log.start')}
        </button>
      </form>
    </div>
  )
}

function Target({ exercise }: { exercise: DraftExercise }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const s = exercise.target
  if (!s) return <p className="font-mono text-[11px] text-muted">{t('log.firstTime')}</p>
  const last = s.last_sets.map((x) => `${x.weight_kg != null ? decimal(x.weight_kg, locale) : t('training.bodyweight')}×${x.reps}${x.rir != null ? ` @${x.rir}` : ''}`).join(' · ')
  const goal = `${s.weight_kg != null ? `${decimal(s.weight_kg, locale)} kg${exercise.bodyweight ? ' +' : ''} × ` : '× '}${s.reps}`
  return (
    <div className="space-y-0.5 font-mono text-[11px] text-muted">
      <p>{t('log.last', { sets: last, when: relativeDay(s.last_date, today, t, locale) })}</p>
      <p className={s.action === 'increase' ? 'text-brass' : ''}>
        {t(s.action === 'increase' ? 'log.goalUp' : 'log.goalReps', { goal, min: s.rep_min, max: s.rep_max })}
        {s.stagnant && <span className="ml-2 text-signal">{t('log.stagnant', { n: s.same_sessions })}</span>}
      </p>
    </div>
  )
}

function SetRow({ index, set, onChange, onRemove }: { index: number; set: DraftSet; onChange: (s: DraftSet) => void; onRemove: () => void }) {
  const { t } = useI18n()
  return (
    <li className={`grid grid-cols-[1.5rem_1fr_1fr_4.2rem_2.75rem] items-center gap-1.5 ${set.done ? '' : 'opacity-80'}`}>
      <button type="button" onClick={onRemove} aria-label={t('log.removeSet', { n: index + 1 })} className="font-mono text-[12px] text-muted hover:text-signal">
        {index + 1}
      </button>
      <input value={set.weight} onChange={(e) => onChange({ ...set, weight: e.target.value })} inputMode="decimal" placeholder="kg" aria-label={t('log.weight', { n: index + 1 })} className={field} />
      <input value={set.reps} onChange={(e) => onChange({ ...set, reps: e.target.value.replace(/\D/g, '') })} inputMode="numeric" placeholder={t('log.reps')} aria-label={t('log.repsN', { n: index + 1 })} className={field} />
      <select value={set.rir} onChange={(e) => onChange({ ...set, rir: e.target.value })} aria-label={t('log.rir', { n: index + 1 })} className={`${field} px-1`}>
        {RIR_OPTIONS.map((v) => (
          <option key={v} value={v}>
            {v === '' ? 'RIR' : v === '4' ? '4+' : v}
          </option>
        ))}
      </select>
      <button
        type="button"
        aria-pressed={set.done}
        aria-label={t('log.done', { n: index + 1 })}
        disabled={!set.reps}
        onClick={() => onChange({ ...set, done: !set.done })}
        className={['grid h-10 place-items-center rounded-md border text-lg transition-colors disabled:opacity-30', set.done ? 'border-chart bg-chart text-paper' : 'border-rule text-muted hover:border-ink'].join(' ')}
      >
        ✓
      </button>
    </li>
  )
}

function ExerciseCard({ exercise, onChange, onRemove }: { exercise: DraftExercise; onChange: (e: DraftExercise) => void; onRemove: () => void }) {
  const { t } = useI18n()
  const setAt = (i: number, s: DraftSet) => onChange({ ...exercise, sets: exercise.sets.map((x, j) => (j === i ? s : x)) })
  const addSet = () => {
    const last = exercise.sets[exercise.sets.length - 1]
    onChange({ ...exercise, sets: [...exercise.sets, { weight: last?.weight ?? '', reps: last?.reps ?? '', rir: '', done: false }] })
  }
  return (
    <section className="rounded-lg border border-rule bg-paper-raised px-3 py-3">
      <div className="mb-1 flex items-start justify-between gap-2">
        <h2 className="font-medium">{exercise.name}</h2>
        <button type="button" onClick={onRemove} aria-label={t('log.removeExercise', { name: exercise.name })} className="px-1 text-muted hover:text-signal">
          ×
        </button>
      </div>
      <Target exercise={exercise} />
      <ul className="mt-3 space-y-1.5">
        {exercise.sets.map((s, i) => (
          <SetRow key={i} index={i} set={s} onChange={(next) => setAt(i, next)} onRemove={() => onChange({ ...exercise, sets: exercise.sets.filter((_, j) => j !== i) })} />
        ))}
      </ul>
      <button type="button" onClick={addSet} className="mt-2 w-full rounded-md border border-dashed border-rule py-1.5 text-sm text-muted hover:border-ink hover:text-ink">
        {t('log.addSet')}
      </button>
    </section>
  )
}

function AddExercise({ onAdd }: { onAdd: (e: DraftExercise) => void }) {
  const { t } = useI18n()
  const exercises = useExercises()
  const [name, setName] = useState('')
  const add = async () => {
    const title = name.trim()
    if (!title) return
    const known = exercises.data?.find((e) => e.name.toLowerCase() === title.toLowerCase() || e.aliases.some((a) => a.toLowerCase() === title.toLowerCase()))
    let item: DraftExercise = { key: newId(), exercise_id: known?.id ?? null, name: known?.name ?? title, bodyweight: known?.bodyweight ?? false, target: null, sets: [{ weight: '', reps: '', rir: '', done: false }] }
    if (known) {
      try {
        item = exerciseFrom(await fetchExerciseTarget(known.id))
      } catch {
        // Offline: add it without a target.
      }
    }
    onAdd(item)
    setName('')
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        void add()
      }}
      className="flex gap-2"
    >
      <input value={name} onChange={(e) => setName(e.target.value)} list="log-exercises" placeholder={t('log.addExercise')} aria-label={t('log.addExercise')} className="min-w-0 flex-1 rounded-md border border-rule bg-paper-raised px-3 py-2 focus:border-brass focus:outline-none" />
      <datalist id="log-exercises">
        {exercises.data?.map((e) => (
          <option key={e.id} value={e.name} />
        ))}
      </datalist>
      <button type="submit" disabled={!name.trim()} className="rounded-md border border-rule px-3 py-2 text-sm hover:border-ink disabled:opacity-40">
        {t('log.add')}
      </button>
    </form>
  )
}

function useMinutesSince(iso: string) {
  const read = () => Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000))
  const [minutes, setMinutes] = useState(read)
  useEffect(() => {
    const id = setInterval(() => setMinutes(read()), 30_000)
    return () => clearInterval(id)
  })
  return minutes
}

function Active({ draft, sync, setDraft, onFinish, onDiscard }: { draft: Draft; sync: Sync; setDraft: (u: (d: Draft) => Draft) => void; onFinish: () => void; onDiscard: () => void }) {
  const { t } = useI18n()
  const minutes = useMinutesSince(draft.started_at)
  const [confirm, setConfirm] = useState(false)
  const done = draft.exercises.reduce((n, e) => n + e.sets.filter((s) => s.done).length, 0)
  const update = (key: string, next: DraftExercise | null) =>
    setDraft((d) => ({ ...d, exercises: next ? d.exercises.map((e) => (e.key === key ? next : e)) : d.exercises.filter((e) => e.key !== key) }))
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <input value={draft.workout_name} onChange={(e) => setDraft((d) => ({ ...d, workout_name: e.target.value }))} aria-label={t('log.name')} className="min-w-0 flex-1 bg-transparent font-display text-3xl font-semibold uppercase focus:outline-none" />
        <span className="shrink-0 font-mono text-[12px] text-muted">{t('log.elapsed', { n: minutes, sets: done })}</span>
      </div>
      <p className={`font-mono text-[11px] ${sync === 'offline' || sync === 'pending' ? 'text-brass' : 'text-muted'}`} aria-live="polite">
        {t(`log.sync.${sync}`)}
      </p>

      {draft.exercises.map((e) => (
        <ExerciseCard key={e.key} exercise={e} onChange={(next) => update(e.key, next)} onRemove={() => update(e.key, null)} />
      ))}
      <AddExercise onAdd={(e) => setDraft((d) => ({ ...d, exercises: [...d.exercises, e] }))} />

      <div className="flex items-center gap-2 pt-2">
        <button type="button" onClick={() => (confirm ? onDiscard() : setConfirm(true))} className={`rounded-md px-3 py-2.5 text-sm ${confirm ? 'bg-signal text-paper' : 'text-muted hover:text-signal'}`}>
          {confirm ? t('log.discardConfirm') : t('log.discard')}
        </button>
        <span className="flex-1" />
        <button type="button" onClick={onFinish} disabled={done === 0} className="rounded-md bg-brass px-5 py-2.5 font-display font-semibold tracking-wide text-brass-ink uppercase disabled:opacity-40">
          {t('log.finish')}
        </button>
      </div>
    </div>
  )
}

/** The workout logger: pick a workout, log sets with weight, reps and RIR, finish. */
export function WorkoutLogPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const client = useQueryClient()
  const { draft, setDraft, sync, push, start, clear } = useDraft()

  const finish = async () => {
    setDraft((d) => ({ ...d, ended_at: nowIso() }))
    // Let the state settle, then send it; offline the draft stays until it goes through.
    setTimeout(async () => {
      if (await push()) {
        clear()
        void client.invalidateQueries({ queryKey: ['training'] })
        toast.success(t('log.saved'))
        navigate('/training')
      } else toast(t('log.savedLater'))
    }, 50)
  }
  const discard = async () => {
    if (draft?.synced_at) {
      try {
        await discardDraft(draft)
      } catch {
        toast.error(t('log.discardFailed'))
        return
      }
    }
    clear()
    void client.invalidateQueries({ queryKey: ['training'] })
  }

  return (
    <>
      <header className="mb-6 flex items-end justify-between gap-3">
        <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase">{t('log.title')}</h1>
        <Link to="/training" className={pill(false)}>
          {t('nav.training')}
        </Link>
      </header>
      {draft ? <Active draft={draft} sync={sync} setDraft={setDraft} onFinish={() => void finish()} onDiscard={() => void discard()} /> : <Start onStart={start} />}
    </>
  )
}
