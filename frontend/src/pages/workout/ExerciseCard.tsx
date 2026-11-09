/** One exercise of the running workout with its sets, its target and adding exercises. */

import { useState } from 'react'

import { useTodayDate } from '../../api/tasks'
import { fetchExerciseTarget, useExercises } from '../../api/training'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useI18n } from '../../i18n/context'
import { decimal, relativeDay } from '../../lib/format'
import { button } from '../../lib/ui'
import { fromKg, type WeightUnit } from '../../lib/units'
import { type DraftExercise, type DraftSet, exerciseFrom, newId, REST_OPTIONS, restLabel, restOf } from '../../lib/workout'
import { field, iconButton } from './styles'

const RIR_OPTIONS = ['', '0', '1', '2', '3', '4']

function Target({ exercise, unit }: { exercise: DraftExercise; unit: WeightUnit }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const s = exercise.target
  if (!s) return <p className="font-mono text-2xs text-muted">{t('log.firstTime')}</p>
  const weight = (kg: number) => decimal(fromKg(kg, unit), locale)
  const last = s.last_sets.map((x) => `${x.weight_kg != null ? weight(x.weight_kg) : t('training.bodyweight')}×${x.reps}${x.rir != null ? ` @${x.rir}` : ''}`).join(' · ')
  const goal = `${s.weight_kg != null ? `${weight(s.weight_kg)} ${unit}${exercise.bodyweight ? ' +' : ''} × ` : '× '}${s.reps}`
  return (
    <div className="space-y-0.5 font-mono text-2xs text-muted">
      <p>{t('log.last', { sets: last, when: relativeDay(s.last_date, today, t, locale) })}</p>
      <p className={s.action === 'increase' ? 'text-brass' : ''}>
        {t(s.action === 'increase' ? 'log.goalUp' : 'log.goalReps', { goal, min: s.rep_min, max: s.rep_max })}
        {s.stagnant && <span className="ml-2 text-signal">{t('log.stagnant', { n: s.same_sessions })}</span>}
      </p>
    </div>
  )
}

function SetRow({ index, set, unit, onChange, onRemove }: { index: number; set: DraftSet; unit: WeightUnit; onChange: (s: DraftSet) => void; onRemove: () => void }) {
  const { t } = useI18n()
  return (
    <li className={`grid grid-cols-[1.75rem_1fr_1fr_4.2rem_2.75rem] items-center gap-1.5 ${set.done ? '' : 'opacity-80'}`}>
      <button type="button" onClick={onRemove} aria-label={t('log.removeSet', { n: index + 1 })} title={t('log.removeSet', { n: index + 1 })} className="h-10 rounded-md font-mono text-data text-muted hover:bg-signal/10 hover:text-signal">
        {index + 1}
      </button>
      <input value={set.weight} onChange={(e) => onChange({ ...set, weight: e.target.value })} inputMode="decimal" placeholder={unit} aria-label={t('log.weight', { n: index + 1 })} className={field} />
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

export function ExerciseCard({
  exercise,
  first,
  last,
  onChange,
  onRemove,
  onMove,
  onSetDone,
  past,
  unit,
}: {
  exercise: DraftExercise
  past: boolean
  unit: WeightUnit
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
          <span className="ml-2 font-mono text-2xs font-normal text-muted">
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
      <Target exercise={exercise} unit={unit} />
      <ul className="mt-3 space-y-1.5">
        {exercise.sets.map((s, i) => (
          <SetRow key={i} index={i} set={s} unit={unit} onChange={(next) => setAt(i, next)} onRemove={() => onChange({ ...exercise, sets: exercise.sets.filter((_, j) => j !== i) })} />
        ))}
      </ul>
      <div className="mt-2 flex items-center gap-2">
        <button type="button" onClick={addSet} className="flex-1 rounded-md border border-dashed border-rule py-1.5 text-sm text-muted hover:border-ink hover:text-ink">
          {t('log.addSet')}
        </button>
        <label className={`flex items-center gap-1.5 font-mono text-2xs text-muted ${past ? 'hidden' : ''}`}>
          {t('log.rest')}
          <select value={restOf(exercise)} onChange={(e) => onChange({ ...exercise, rest: Number(e.target.value) })} aria-label={t('log.restFor')} className="rounded-md border border-rule bg-paper px-1.5 py-1 text-data text-ink">
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

export function AddExercise({ unit, onAdd }: { unit: WeightUnit; onAdd: (e: DraftExercise) => void }) {
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
        item = exerciseFrom(await fetchExerciseTarget(known.id), unit)
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
