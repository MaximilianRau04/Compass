import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { useTodayDate } from '../api/tasks'
import { fetchExerciseTarget, fetchTemplate, useExercises, useSaveTemplate, useTemplates, useWorkoutNames } from '../api/training'
import type { WorkoutTemplate } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { SectionLabel } from '../components/Layout'
import { TemplateEditor } from '../components/TemplateEditor'
import { useI18n } from '../i18n/context'
import { addDays, decimal, localDay, pill, relativeDay } from '../lib/format'
import { button } from '../lib/ui'
import {
  clock,
  type Draft,
  type DraftExercise,
  type DraftSet,
  discardDraft,
  exerciseFrom,
  loadDraft,
  loadRest,
  localIso,
  localParts,
  newId,
  REST_OPTIONS,
  restLabel,
  type RestTimer,
  restOf,
  sendDraft,
  storeDraft,
  storeRest,
} from '../lib/workout'

type Sync = 'saved' | 'saving' | 'pending' | 'offline'

const nowIso = () => new Date().toISOString()

const RIR_OPTIONS = ['', '0', '1', '2', '3', '4']
const field = 'w-full min-w-0 rounded-md border border-rule bg-paper px-2 py-2 text-center font-mono text-[15px] tabular-nums focus:border-brass focus:outline-none'
const iconButton = 'grid h-8 w-8 place-items-center rounded-md text-muted hover:bg-paper hover:text-ink disabled:opacity-30'

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
    storeRest(null)
    setDraftState(null)
  }
  return { draft, setDraft, sync, push, start, clear }
}

/** The current time, every second. */
function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const id = setInterval(tick, 1000)
    // Timers sleep in the background; catch up as soon as the page is back.
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [])
  return now
}

/** Keeps the screen on during the workout, so the clock and the rest timer stay in view. */
function useWakeLock(enabled: boolean) {
  useEffect(() => {
    if (!enabled || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let gone = false
    const acquire = async () => {
      if (document.visibilityState !== 'visible' || gone) return
      try {
        lock = await navigator.wakeLock.request('screen')
      } catch {
        // Battery saver or not allowed: the timers still work, the screen just may turn off.
      }
    }
    void acquire()
    document.addEventListener('visibilitychange', acquire)
    return () => {
      gone = true
      document.removeEventListener('visibilitychange', acquire)
      void lock?.release().catch(() => undefined)
    }
  }, [enabled])
}

let audio: AudioContext | null = null

/** Audio has to be started by a tap; marking a set done is one, so the end of the rest can beep. */
function unlockAudio() {
  try {
    audio ??= new AudioContext()
    if (audio.state === 'suspended') void audio.resume()
  } catch {
    audio = null
  }
}

function beep() {
  if (!audio) return
  const start = audio.currentTime
  for (const [offset, freq] of [
    [0, 880],
    [0.22, 880],
    [0.44, 1320],
  ]) {
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.0001, start + offset)
    gain.gain.exponentialRampToValueAtTime(0.25, start + offset + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.18)
    osc.connect(gain).connect(audio.destination)
    osc.start(start + offset)
    osc.stop(start + offset + 0.2)
  }
}

function useRestTimer() {
  const [rest, setRestState] = useState<RestTimer | null>(() => loadRest())
  const setRest = useCallback((next: RestTimer | null) => {
    storeRest(next)
    setRestState(next)
  }, [])
  return { rest, setRest }
}

function RestBar({ rest, now, onChange }: { rest: RestTimer; now: number; onChange: (r: RestTimer | null) => void }) {
  const { t } = useI18n()
  // `now` ticks once a second, so right after the start it can lag behind: never above the full rest.
  const left = Math.min(rest.seconds, Math.ceil((new Date(rest.ends_at).getTime() - now) / 1000))
  const over = left <= 0
  const alerted = useRef<string | null>(null)

  // Once per rest: vibrate, beep and, with the phone in the pocket, a notification.
  useEffect(() => {
    if (!over || alerted.current === rest.ends_at) return
    alerted.current = rest.ends_at
    // Back on the page long after the end (reload, phone in the pocket): no alarm any more.
    if (left < -60) return
    navigator.vibrate?.([250, 120, 250])
    beep()
    if (document.visibilityState === 'hidden' && 'Notification' in window && Notification.permission === 'granted') {
      void navigator.serviceWorker?.ready
        .then((r) => r.showNotification(t('log.restOver'), { body: t('log.restNext', { name: rest.next }), tag: 'compass-rest', silent: false }))
        .catch(() => undefined)
    }
  }, [over, left, rest, t])

  // A few seconds after the end it gets out of the way.
  useEffect(() => {
    if (left > -8) return
    onChange(null)
  }, [left, onChange])

  const shift = (by: number) => {
    const ends = Math.max(now, new Date(rest.ends_at).getTime()) + by * 1000
    onChange({ ...rest, ends_at: new Date(Math.max(now + 1000, ends)).toISOString(), seconds: Math.max(1, rest.seconds + by) })
  }
  const progress = over ? 1 : Math.min(1, Math.max(0, 1 - left / rest.seconds))

  return (
    <div
      role="timer"
      aria-live={over ? 'assertive' : 'off'}
      className="fixed inset-x-3 bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-20 mx-auto max-w-xl overflow-hidden rounded-xl border border-rule bg-paper-raised/95 shadow-lg backdrop-blur sm:bottom-6"
    >
      <div className="h-1 bg-rule">
        <div className={`h-1 transition-[width] duration-1000 ease-linear ${over ? 'bg-brass' : 'bg-chart'}`} style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="flex items-center gap-3 px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <p className={`font-mono text-[11px] tracking-wider uppercase ${over ? 'text-brass' : 'text-muted'}`}>{over ? t('log.restOver') : t('log.rest')}</p>
          <p className="truncate text-sm text-muted">{t('log.restNext', { name: rest.next })}</p>
        </div>
        <span className={`font-mono text-3xl font-medium tabular-nums ${over ? 'text-brass' : ''}`}>{over ? '0:00' : clock(left)}</span>
        {!over && (
          <>
            <button type="button" onClick={() => shift(-15)} aria-label={t('log.restLess')} className={button('secondary', 'sm')}>
              −15
            </button>
            <button type="button" onClick={() => shift(15)} aria-label={t('log.restMore')} className={button('secondary', 'sm')}>
              +15
            </button>
          </>
        )}
        <button type="button" onClick={() => onChange(null)} className={button(over ? 'primary' : 'quiet', 'sm')}>
          {over ? t('log.restDone') : t('log.restSkip')}
        </button>
      </div>
    </div>
  )
}

function TemplateCard({ template, onStart, onEdit, disabled }: { template: WorkoutTemplate; onStart: () => void; onEdit: () => void; disabled: boolean }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  return (
    <li className="flex rounded-lg border border-rule bg-paper-raised hover:border-ink">
      <button type="button" disabled={disabled} onClick={onStart} className="min-w-0 flex-1 px-3 py-3 text-left disabled:opacity-50">
        <span className="block truncate font-medium">{template.name}</span>
        <span className="block font-mono text-[11px] text-muted">
          {t('log.exercisesN', { n: template.exercises.length })} · {template.last_at ? relativeDay(localDay(template.last_at), today, t, locale) : t('log.neverTrained')}
        </span>
      </button>
      <button type="button" onClick={onEdit} aria-label={t('log.edit', { name: template.name })} className="border-l border-rule px-3 text-muted hover:text-ink">
        ✎
      </button>
    </li>
  )
}

const input = 'rounded-md border border-rule bg-paper-raised px-3 py-2 font-mono text-[14px] focus:border-brass focus:outline-none'

/** When a workout entered afterwards took place. */
function PastFields({ day, time, minutes, onChange, max }: { day: string; time: string; minutes: string; onChange: (v: { day?: string; time?: string; minutes?: string }) => void; max: string }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1 font-mono text-[11px] text-muted">
        {t('log.pastDay')}
        <input type="date" value={day} max={max} onChange={(e) => onChange({ day: e.target.value })} className={input} />
      </label>
      <label className="flex flex-col gap-1 font-mono text-[11px] text-muted">
        {t('log.pastTime')}
        <input type="time" value={time} onChange={(e) => onChange({ time: e.target.value })} className={input} />
      </label>
      <label className="flex flex-col gap-1 font-mono text-[11px] text-muted">
        {t('log.pastMinutes')}
        <input value={minutes} inputMode="numeric" onChange={(e) => onChange({ minutes: e.target.value.replace(/\D/g, '').slice(0, 3) })} className={`${input} w-24`} />
      </label>
    </div>
  )
}

function Start({ onStart }: { onStart: (d: Draft) => void }) {
  const { t, locale } = useI18n()
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
      exercises = template.exercises.map(exerciseFrom)
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
            <p className={`mt-2 font-mono text-[11px] ${pastValid ? 'text-muted' : 'text-signal'}`}>{pastValid ? t('log.pastHint') : t('log.pastInvalid')}</p>
          </div>
        )}
      </div>

      <section>
        <SectionLabel count={templates.data?.length || undefined}>{t('log.templates')}</SectionLabel>
        <p className="mt-1 font-mono text-[11px] text-muted">{t('log.templatesHint')}</p>
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
                  <span className="font-mono text-[11px] text-muted">{relativeDay(localDay(w.last_at), today, t, locale)}</span>
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
    <li className={`grid grid-cols-[1.75rem_1fr_1fr_4.2rem_2.75rem] items-center gap-1.5 ${set.done ? '' : 'opacity-80'}`}>
      <button type="button" onClick={onRemove} aria-label={t('log.removeSet', { n: index + 1 })} title={t('log.removeSet', { n: index + 1 })} className="h-10 rounded-md font-mono text-[12px] text-muted hover:bg-signal/10 hover:text-signal">
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

function ExerciseCard({
  exercise,
  first,
  last,
  onChange,
  onRemove,
  onMove,
  onSetDone,
  past,
}: {
  exercise: DraftExercise
  past: boolean
  first: boolean
  last: boolean
  onChange: (e: DraftExercise) => void
  onRemove: () => void
  onMove: (by: -1 | 1) => void
  onSetDone: (exercise: DraftExercise) => void
}) {
  const { t } = useI18n()
  const [confirm, setConfirm] = useState(false)
  const done = exercise.sets.filter((s) => s.done).length
  const setAt = (i: number, s: DraftSet) => {
    const next = { ...exercise, sets: exercise.sets.map((x, j) => (j === i ? s : x)) }
    onChange(next)
    if (s.done && !exercise.sets[i].done) onSetDone(next)
  }
  const addSet = () => {
    const prev = exercise.sets[exercise.sets.length - 1]
    onChange({ ...exercise, sets: [...exercise.sets, { weight: prev?.weight ?? '', reps: prev?.reps ?? '', rir: '', done: false }] })
  }
  const complete = exercise.sets.length > 0 && done === exercise.sets.length
  return (
    <section className={`rounded-lg border bg-paper-raised px-3 py-3 ${complete ? 'border-chart/50' : 'border-rule'}`}>
      <div className="mb-1 flex items-start gap-1">
        <h2 className="min-w-0 flex-1 pt-1 font-medium">
          {exercise.name}
          <span className="ml-2 font-mono text-[11px] font-normal text-muted">
            {done}/{exercise.sets.length}
          </span>
        </h2>
        <button type="button" disabled={first} onClick={() => onMove(-1)} aria-label={t('log.moveUp', { name: exercise.name })} className={iconButton}>
          ↑
        </button>
        <button type="button" disabled={last} onClick={() => onMove(1)} aria-label={t('log.moveDown', { name: exercise.name })} className={iconButton}>
          ↓
        </button>
        <button type="button" onClick={() => (done > 0 ? setConfirm(true) : onRemove())} aria-label={t('log.removeExercise', { name: exercise.name })} className={`${iconButton} hover:bg-signal/10 hover:text-signal`}>
          ×
        </button>
      </div>
      <Target exercise={exercise} />
      <ul className="mt-3 space-y-1.5">
        {exercise.sets.map((s, i) => (
          <SetRow key={i} index={i} set={s} onChange={(next) => setAt(i, next)} onRemove={() => onChange({ ...exercise, sets: exercise.sets.filter((_, j) => j !== i) })} />
        ))}
      </ul>
      <div className="mt-2 flex items-center gap-2">
        <button type="button" onClick={addSet} className="flex-1 rounded-md border border-dashed border-rule py-1.5 text-sm text-muted hover:border-ink hover:text-ink">
          {t('log.addSet')}
        </button>
        <label className={`flex items-center gap-1.5 font-mono text-[11px] text-muted ${past ? 'hidden' : ''}`}>
          {t('log.rest')}
          <select value={restOf(exercise)} onChange={(e) => onChange({ ...exercise, rest: Number(e.target.value) })} aria-label={t('log.restFor')} className="rounded-md border border-rule bg-paper px-1.5 py-1 text-[12px] text-ink">
            {REST_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {restLabel(s, t('log.restNone'))}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('log.removeExerciseTitle')}
        description={t('log.removeExerciseText', { name: exercise.name, n: done })}
        confirm={t('log.remove')}
        onConfirm={onRemove}
      />
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
      <button type="submit" disabled={!name.trim()} className={button('secondary')}>
        {t('log.add')}
      </button>
    </form>
  )
}

/** The exercise of the next open set, after the one just done. */
function nextUp(exercises: DraftExercise[], current: DraftExercise): string | null {
  if (current.sets.some((s) => !s.done)) return current.name
  const from = exercises.findIndex((e) => e.key === current.key)
  const rest = [...exercises.slice(from + 1), ...exercises.slice(0, from)]
  return rest.find((e) => e.sets.some((s) => !s.done))?.name ?? null
}

function Active({ draft, sync, setDraft, onFinish, onDiscard }: { draft: Draft; sync: Sync; setDraft: (u: (d: Draft) => Draft) => void; onFinish: () => void; onDiscard: () => void }) {
  const { t } = useI18n()
  const now = useNow()
  const past = draft.backfill
  useWakeLock(!past)
  const { rest, setRest } = useRestTimer()
  const templates = useTemplates()
  const saveTemplate = useSaveTemplate()
  const [dialog, setDialog] = useState<'discard' | 'finish' | 'template' | null>(null)

  const done = draft.exercises.reduce((n, e) => n + e.sets.filter((s) => s.done).length, 0)
  const open = draft.exercises.reduce((n, e) => n + e.sets.filter((s) => !s.done).length, 0)
  const elapsed = (now - new Date(draft.started_at).getTime()) / 1000

  const update = (key: string, next: DraftExercise | null) =>
    setDraft((d) => ({ ...d, exercises: next ? d.exercises.map((e) => (e.key === key ? next : e)) : d.exercises.filter((e) => e.key !== key) }))
  const move = (i: number, by: -1 | 1) =>
    setDraft((d) => {
      const list = [...d.exercises]
      ;[list[i], list[i + by]] = [list[i + by], list[i]]
      return { ...d, exercises: list }
    })
  const setDone = (exercise: DraftExercise) => {
    if (past) return // entered afterwards: nobody rests now
    unlockAudio()
    const seconds = restOf(exercise)
    const exercises = draft.exercises.map((e) => (e.key === exercise.key ? exercise : e))
    const next = nextUp(exercises, exercise)
    if (seconds === 0 || next === null) return setRest(null)
    setRest({ ends_at: new Date(Date.now() + seconds * 1000).toISOString(), seconds, next })
  }

  const existing = templates.data?.find((x) => x.name.toLowerCase() === draft.workout_name.trim().toLowerCase())
  const storeTemplate = () =>
    saveTemplate.mutate(
      {
        id: existing?.id,
        data: {
          name: draft.workout_name.trim(),
          exercises: draft.exercises.map((e) => ({ exercise_id: e.exercise_id, name: e.name, sets: Math.max(1, e.sets.length), rest_seconds: restOf(e) })),
        },
      },
      { onSuccess: (saved) => toast(t('log.templateSaved', { name: saved.name })), onError: (error) => toast.error(error.message) },
    )

  return (
    <div className="space-y-4">
      <div>
        <input value={draft.workout_name} onChange={(e) => setDraft((d) => ({ ...d, workout_name: e.target.value }))} aria-label={t('log.name')} className="w-full min-w-0 bg-transparent font-display text-3xl font-semibold uppercase focus:outline-none" />
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          {past ? (
            <PastFields
              {...localParts(draft.started_at)}
              minutes={String(past.minutes || '')}
              max={localParts(nowIso()).day}
              onChange={(v) =>
                setDraft((d) => {
                  const parts = { ...localParts(d.started_at), ...v }
                  const started = v.day !== undefined || v.time !== undefined ? localIso(parts.day, parts.time) : d.started_at
                  return { ...d, started_at: started, backfill: { minutes: v.minutes !== undefined ? Number(v.minutes) : (d.backfill?.minutes ?? 60) } }
                })
              }
            />
          ) : (
            <span className="font-mono text-2xl font-medium tabular-nums" aria-label={t('log.elapsedLabel')}>
              {clock(elapsed)}
            </span>
          )}
          <span className="font-mono text-[12px] text-muted">
            {t('log.setsDone', { done, total: done + open })}
          </span>
        </div>
        <p className={`font-mono text-[11px] ${sync === 'offline' || sync === 'pending' ? 'text-brass' : 'text-muted'}`} aria-live="polite">
          {t(`log.sync.${sync}`)}
        </p>
      </div>

      {draft.exercises.map((e, i) => (
        <ExerciseCard
          key={e.key}
          exercise={e}
          first={i === 0}
          last={i === draft.exercises.length - 1}
          onChange={(next) => update(e.key, next)}
          onRemove={() => update(e.key, null)}
          onMove={(by) => move(i, by)}
          onSetDone={setDone}
          past={Boolean(past)}
        />
      ))}
      <AddExercise onAdd={(e) => setDraft((d) => ({ ...d, exercises: [...d.exercises, e] }))} />

      <div className="flex flex-wrap items-center gap-2 border-t border-rule pt-4">
        <button type="button" onClick={() => setDialog('discard')} className={button('danger')}>
          {t('log.discard')}
        </button>
        <button type="button" disabled={draft.exercises.length === 0 || !draft.workout_name.trim() || saveTemplate.isPending} onClick={() => (existing ? setDialog('template') : storeTemplate())} className={button('secondary')}>
          {t('log.saveTemplate')}
        </button>
        <span className="flex-1" />
        <button type="button" onClick={() => (open > 0 ? setDialog('finish') : onFinish())} disabled={done === 0} className={`${button('primary', 'lg')} font-display font-semibold tracking-wide uppercase`}>
          {t('log.finish')}
        </button>
      </div>

      {/* Room for the rest bar, so it never covers the last set. */}
      {rest && !past && <div className="h-20" />}
      {rest && !past && <RestBar rest={rest} now={now} onChange={setRest} />}

      <ConfirmDialog
        open={dialog === 'discard'}
        onOpenChange={(o) => setDialog(o ? 'discard' : null)}
        title={t('log.discardTitle')}
        description={done > 0 ? t('log.discardText', { n: done }) : t('log.discardTextEmpty')}
        confirm={t('log.discardYes')}
        onConfirm={onDiscard}
      />
      <ConfirmDialog
        open={dialog === 'finish'}
        onOpenChange={(o) => setDialog(o ? 'finish' : null)}
        title={t('log.finishTitle')}
        description={t('log.finishText', { n: open })}
        confirm={t('log.finish')}
        onConfirm={onFinish}
        danger={false}
      />
      <ConfirmDialog
        open={dialog === 'template'}
        onOpenChange={(o) => setDialog(o ? 'template' : null)}
        title={t('log.templateUpdateTitle')}
        description={t('log.templateUpdateText', { name: existing?.name ?? '' })}
        confirm={t('log.templateUpdate')}
        onConfirm={storeTemplate}
        danger={false}
      />
    </div>
  )
}

/** The workout logger: pick or build a workout, log sets with weight, reps and RIR, rest, finish. */
export function WorkoutLogPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const client = useQueryClient()
  const { draft, setDraft, sync, push, start, clear } = useDraft()

  const finish = async () => {
    // Entered afterwards: it ended when its duration says, not now.
    setDraft((d) => ({ ...d, ended_at: d.backfill ? new Date(new Date(d.started_at).getTime() + Math.max(1, d.backfill.minutes) * 60_000).toISOString() : nowIso() }))
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
