import { post } from '../api/client'
import type { SessionBrief, TemplateExercise } from '../api/types'
import { toKg, type WeightUnit, weightField } from './units'

/*
 * The running workout lives on the phone (localStorage) and is sent whole after every change, so
 * a dead spot in the gym loses nothing: the next send carries everything, and the server updates
 * the same session by its client id.
 */

export interface DraftSet {
  weight: string
  reps: string
  rir: string
  done: boolean
}

export interface DraftExercise {
  key: string
  exercise_id: number | null
  name: string
  bodyweight: boolean
  target: TemplateExercise['suggestion']
  sets: DraftSet[]
  /** Rest after each set in seconds; missing in drafts from before rest timers. */
  rest?: number
}

export interface Draft {
  client_id: string
  workout_name: string
  started_at: string
  ended_at: string | null
  exercises: DraftExercise[]
  /** Last change and the last change the server confirmed (ISO times). */
  changed_at: string
  synced_at: string | null
  /** Entered afterwards: started_at is in the past and the session lasted this long. No clock,
   * no rest timer. */
  backfill?: { minutes: number }
  /** Unit the weights are typed in, fixed when the workout starts; missing in older drafts (kg). */
  unit?: WeightUnit
}

const KEY = 'compass.workout'
const REST_KEY = 'compass.workout.rest'

export const REST_DEFAULT = 90
export const REST_OPTIONS = [0, 30, 45, 60, 90, 120, 150, 180, 240, 300]
export const restOf = (e: DraftExercise) => e.rest ?? REST_DEFAULT

/** The running rest between two sets. Kept apart from the draft, so it is not sent anywhere. */
export interface RestTimer {
  /** ISO time the rest is over */
  ends_at: string
  seconds: number
  /** Exercise the next set belongs to */
  next: string
}

export function loadRest(): RestTimer | null {
  try {
    const raw = localStorage.getItem(REST_KEY)
    return raw ? (JSON.parse(raw) as RestTimer) : null
  } catch {
    return null
  }
}

export function storeRest(rest: RestTimer | null) {
  try {
    if (rest) localStorage.setItem(REST_KEY, JSON.stringify(rest))
    else localStorage.removeItem(REST_KEY)
  } catch {
    // The timer still runs while the page is open.
  }
}

/** A rest option for a select: "1:30", or the word for none. */
export const restLabel = (seconds: number, none: string) => (seconds === 0 ? none : clock(seconds))

/** 75 s → "1:15", 3725 s → "1:02:05". */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function loadDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Draft) : null
  } catch {
    return null
  }
}

export function storeDraft(draft: Draft | null) {
  try {
    if (draft) localStorage.setItem(KEY, JSON.stringify(draft))
    else localStorage.removeItem(KEY)
  } catch {
    // Private mode or full storage: the in-memory draft still syncs while the page is open.
  }
}

export function newId(): string {
  return crypto.randomUUID?.() ?? `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`
}

const num = (value: string) => {
  const n = Number(value.replace(',', '.'))
  return value.trim() === '' || !Number.isFinite(n) ? null : n
}

/** Planned sets from the progression target: as many as the template plans (or as last time),
 * at the target. */
export function exerciseFrom(t: TemplateExercise, unit: WeightUnit): DraftExercise {
  const s = t.suggestion
  const count = Math.max(1, t.sets ?? s?.last_set_count ?? 3)
  const weight = s?.weight_kg != null ? weightField(s.weight_kg, unit) : ''
  return {
    key: newId(),
    exercise_id: t.exercise_id,
    name: t.name,
    bodyweight: t.bodyweight,
    target: s,
    rest: t.rest_seconds ?? REST_DEFAULT,
    sets: Array.from({ length: count }, () => ({ weight, reps: s ? String(s.reps) : '', rir: '', done: false })),
  }
}

/** Only sets marked done are sent, with the weight in kg; planned ones stay on the phone. */
export function toPayload(draft: Draft) {
  const kg = (weight: string) => {
    const value = num(weight)
    return value === null ? null : toKg(value, draft.unit ?? 'kg')
  }
  return {
    client_id: draft.client_id,
    workout_name: draft.workout_name,
    started_at: draft.started_at,
    ended_at: draft.ended_at,
    exercises: draft.exercises.map((e) => ({
      exercise_id: e.exercise_id,
      name: e.name,
      sets: e.sets
        .filter((s) => s.done && num(s.reps) !== null)
        .map((s) => ({ weight_kg: kg(s.weight), reps: num(s.reps), rir: num(s.rir) })),
    })),
  }
}

export const sendDraft = (draft: Draft) => post<SessionBrief>('/training/log', toPayload(draft))
export const discardDraft = (draft: Draft) => post<null>(`/training/log/${draft.client_id}/discard`)

/** "2026-11-05" and "18:30" in the phone's time zone as an ISO time. */
export const localIso = (day: string, time: string) => new Date(`${day}T${time}`).toISOString()

/** An ISO time as the phone's local day and time, for date and time inputs. */
export function localParts(iso: string): { day: string; time: string } {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return { day: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` }
}
