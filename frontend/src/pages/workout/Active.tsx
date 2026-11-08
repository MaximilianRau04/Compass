/** The running workout: clock, rest timer, exercises and finishing. */

import { useState } from 'react'
import { toast } from 'sonner'

import { useSaveTemplate, useTemplates } from '../../api/training'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useI18n } from '../../i18n/context'
import { button } from '../../lib/ui'
import { clock, type Draft, type DraftExercise, localIso, localParts, restOf } from '../../lib/workout'
import { AddExercise, ExerciseCard } from './ExerciseCard'
import { RestBar } from './RestBar'
import { PastFields } from './Start'
import { nowIso, type Sync, unlockAudio, useNow, useRestTimer, useWakeLock } from './hooks'

/** The exercise of the next open set, after the one just done. */
function nextUp(exercises: DraftExercise[], current: DraftExercise): string | null {
  if (current.sets.some((s) => !s.done)) return current.name
  const from = exercises.findIndex((e) => e.key === current.key)
  const rest = [...exercises.slice(from + 1), ...exercises.slice(0, from)]
  return rest.find((e) => e.sets.some((s) => !s.done))?.name ?? null
}

export function Active({ draft, sync, setDraft, onFinish, onDiscard }: { draft: Draft; sync: Sync; setDraft: (u: (d: Draft) => Draft) => void; onFinish: () => void; onDiscard: () => void }) {
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
        <p className={`font-mono text-2xs ${sync === 'offline' || sync === 'pending' ? 'text-brass' : 'text-muted'}`} aria-live="polite">
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
