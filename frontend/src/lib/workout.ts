import { post } from '../api/client'
import type { SessionBrief, TemplateExercise } from '../api/types'

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
}

const KEY = 'compass.workout'

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

/** Planned sets from the progression target: as many as last time, at the target. */
export function exerciseFrom(t: TemplateExercise): DraftExercise {
  const s = t.suggestion
  const count = Math.max(1, s?.last_set_count ?? 3)
  const weight = s?.weight_kg != null ? String(s.weight_kg) : ''
  return {
    key: newId(),
    exercise_id: t.exercise_id,
    name: t.name,
    bodyweight: t.bodyweight,
    target: s,
    sets: Array.from({ length: count }, () => ({ weight, reps: s ? String(s.reps) : '', rir: '', done: false })),
  }
}

/** Only sets marked done are sent; planned ones stay on the phone. */
export function toPayload(draft: Draft) {
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
        .map((s) => ({ weight_kg: num(s.weight), reps: num(s.reps), rir: num(s.rir) })),
    })),
  }
}

export const sendDraft = (draft: Draft) => post<SessionBrief>('/training/log', toPayload(draft))
export const discardDraft = (draft: Draft) => post<null>(`/training/log/${draft.client_id}/discard`)
