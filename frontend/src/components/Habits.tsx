import { useState } from 'react'
import { toast } from 'sonner'

import { type Habit, type HabitRule, useArchiveHabit, useCheckHabit, useCreateHabit, useHabits } from '../api/habits'
import { useI18n } from '../i18n/context'
import { button } from '../lib/ui'
import { ConfirmDialog } from './ConfirmDialog'
import { SectionLabel } from './Layout'

const RULES: (HabitRule | '')[] = ['', 'steps_goal', 'protein_goal', 'sleep_need', 'journal']
const field = 'rounded-md border border-rule bg-paper px-3 py-2 focus:border-brass focus:outline-none'

function Row({ habit, today }: { habit: Habit; today: string }) {
  const { t } = useI18n()
  const check = useCheckHabit()
  const archive = useArchiveHabit()
  const [confirm, setConfirm] = useState(false)
  const manual = habit.rule === null
  const ruleText = habit.rule ? t(`habits.rule.${habit.rule}`) : undefined
  return (
    <li className="flex items-center gap-3 py-2">
      <button
        type="button"
        disabled={!manual || check.isPending}
        aria-pressed={habit.done_today}
        aria-label={t(habit.done_today ? 'habits.untick' : 'habits.tick', { name: habit.name })}
        title={ruleText}
        onClick={() => check.mutate({ id: habit.id, day: today, done: !habit.done_today }, { onError: (error) => toast.error(error.message) })}
        className={`grid h-5 w-5 shrink-0 place-items-center rounded-md border-[1.5px] ${habit.done_today ? 'border-sea bg-sea text-paper' : 'border-muted/60'} ${manual ? 'hover:border-ink' : 'cursor-default'}`}
      >
        {habit.done_today && '✓'}
      </button>
      <span className="min-w-0 flex-1">
        {habit.name}
        {ruleText && <span className="block font-mono text-2xs text-muted">{ruleText}</span>}
      </span>
      <span className="font-mono text-2xs text-muted" aria-label={t('habits.streak', { n: habit.streak })}>
        {habit.streak > 0 ? `${habit.streak} ↯` : ''}
      </span>
      <span className="hidden gap-px sm:flex" aria-hidden>
        {habit.days.slice(-14).map((done, i) => (
          <span key={i} className={`h-3 w-1.5 rounded-sm ${done ? 'bg-sea' : 'bg-rule'}`} />
        ))}
      </span>
      <button type="button" onClick={() => setConfirm(true)} aria-label={t('habits.remove', { name: habit.name })} className="text-muted hover:text-signal">
        ×
      </button>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('habits.removeTitle')}
        description={t('habits.removeText', { name: habit.name })}
        confirm={t('habits.removeConfirm')}
        onConfirm={() => archive.mutate(habit.id, { onError: (error) => toast.error(error.message) })}
      />
    </li>
  )
}

/** Daily habits with their streak and the last two weeks; some are ticked from the data. */
export function Habits({ today }: { today: string }) {
  const { t } = useI18n()
  const habits = useHabits()
  const create = useCreateHabit()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [rule, setRule] = useState<HabitRule | ''>('')
  if (!habits.data) return null
  const done = habits.data.filter((h) => h.done_today).length
  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <SectionLabel count={habits.data.length ? done : undefined}>{t('habits.title')}</SectionLabel>
        <button type="button" onClick={() => setAdding(!adding)} className="font-mono text-2xs text-brass hover:underline">
          {adding ? t('common.cancel') : t('habits.add')}
        </button>
      </div>
      {habits.data.length === 0 && !adding && <p className="py-1 text-sm text-muted">{t('habits.empty')}</p>}
      <ul className="divide-y divide-rule/60">
        {habits.data.map((h) => (
          <Row key={h.id} habit={h} today={today} />
        ))}
      </ul>
      {adding && (
        <form
          className="mt-2 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            create.mutate(
              { name: name.trim(), rule: rule || null },
              {
                onSuccess: () => {
                  setName('')
                  setRule('')
                  setAdding(false)
                },
                onError: (error) => toast.error(error.message),
              },
            )
          }}
        >
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('habits.name')} aria-label={t('habits.name')} className={`${field} min-w-0 flex-1`} />
          <select value={rule} onChange={(e) => setRule(e.target.value as HabitRule | '')} aria-label={t('habits.ruleLabel')} className={field}>
            {RULES.map((r) => (
              <option key={r} value={r}>
                {r ? t(`habits.rule.${r}`) : t('habits.manual')}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!name.trim() || create.isPending} className={button('primary')}>
            {t('habits.save')}
          </button>
        </form>
      )}
    </section>
  )
}
