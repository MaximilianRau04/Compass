import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { toast } from 'sonner'

import { useAddNight, useDeleteNight, useManualNights } from '../api/sleep'
import { useTodayDate } from '../api/tasks'
import type { SleepNight } from '../api/types'
import { useI18n } from '../i18n/context'
import { clockTime, relativeDay } from '../lib/format'
import { hours } from '../lib/health'
import { button, overlay } from '../lib/ui'
import { localIso } from '../lib/workout'
import { ConfirmDialog } from './ConfirmDialog'
import { SectionLabel } from './Layout'

const input = 'w-full rounded-md border border-rule bg-paper px-3 py-2 font-mono text-[14px] focus:border-brass focus:outline-none'
const label = 'flex flex-col gap-1 font-mono text-[11px] tracking-wider text-muted uppercase'

/** Bedtime after the wake-up time (23:30 → 07:00) means the evening before the wake-up day. */
function nightTimes(wakeDay: string, bed: string, wake: string) {
  const end = new Date(localIso(wakeDay, wake))
  const start = new Date(localIso(wakeDay, bed))
  if (bed >= wake) start.setDate(start.getDate() - 1)
  return { start, end }
}

function Form({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const today = useTodayDate()
  const add = useAddNight()
  const [day, setDay] = useState(today)
  const [bed, setBed] = useState('23:00')
  const [wake, setWake] = useState('07:00')
  const [awake, setAwake] = useState('')
  // When the form opened; enough to tell a night in the future.
  const [openedAt] = useState(() => Date.now())

  const { start, end } = nightTimes(day, bed, wake)
  const inBed = Math.round((end.getTime() - start.getTime()) / 60_000)
  const asleep = inBed - (Number(awake) || 0)
  const valid = Boolean(day && bed && wake) && inBed > 0 && inBed <= 16 * 60 && asleep > 0 && end.getTime() <= openedAt + 5 * 60_000

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (!valid) return
        add.mutate(
          { start_at: start.toISOString(), end_at: end.toISOString(), awake_minutes: Number(awake) || 0 },
          {
            onSuccess: (n) => {
              toast(t('sleepLog.saved', { time: hours(n.asleep_minutes) }))
              onClose()
            },
            onError: (error) => toast.error(error.message),
          },
        )
      }}
    >
      <Dialog.Title className="font-display text-2xl font-semibold tracking-wide uppercase">{t('sleepLog.title')}</Dialog.Title>
      <Dialog.Description className="text-sm text-muted">{t('sleepLog.hint')}</Dialog.Description>
      <div className="grid grid-cols-2 gap-3">
        <label className={`${label} col-span-2`}>
          {t('sleepLog.wakeDay')}
          <input type="date" value={day} max={today} onChange={(e) => setDay(e.target.value)} className={input} />
        </label>
        <label className={label}>
          {t('sleepLog.bed')}
          <input type="time" value={bed} onChange={(e) => setBed(e.target.value)} className={input} />
        </label>
        <label className={label}>
          {t('sleepLog.wake')}
          <input type="time" value={wake} onChange={(e) => setWake(e.target.value)} className={input} />
        </label>
        <label className={`${label} col-span-2`}>
          {t('sleepLog.awake')}
          <input value={awake} inputMode="numeric" placeholder="0" onChange={(e) => setAwake(e.target.value.replace(/\D/g, '').slice(0, 3))} className={input} />
        </label>
      </div>
      <p className={`font-mono text-[12px] ${valid ? 'text-muted' : 'text-signal'}`} aria-live="polite">
        {valid ? t('sleepLog.preview', { asleep: hours(asleep), inBed: hours(inBed) }) : t('sleepLog.invalid')}
      </p>
      <div className="flex justify-end gap-2 border-t border-rule pt-4">
        <Dialog.Close className={button('quiet')}>{t('common.cancel')}</Dialog.Close>
        <button type="submit" disabled={!valid || add.isPending} className={button('primary')}>
          {t('editor.save')}
        </button>
      </div>
    </form>
  )
}

/** The button that opens the form, for the page header. */
export function SleepEntryButton() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className={button('secondary')}>{t('sleepLog.add')}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto rounded-t-2xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[28rem] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl">
          {open && <Form onClose={() => setOpen(false)} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function ManualRow({ night, today }: { night: SleepNight; today: string }) {
  const { t, locale } = useI18n()
  const remove = useDeleteNight()
  const [confirm, setConfirm] = useState(false)
  const when = relativeDay(night.local_date, today, t, locale)
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span>
        <span className="font-medium">{hours(night.asleep_minutes)}</span>
        <span className="ml-2 font-mono text-[11px] text-muted">
          {when} · {clockTime(night.start_at, locale)}–{clockTime(night.end_at, locale)}
        </span>
      </span>
      <button type="button" onClick={() => setConfirm(true)} className={button('danger', 'sm')}>
        {t('training.delete')}
      </button>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('sleepLog.deleteTitle')}
        description={t('sleepLog.deleteText', { when })}
        confirm={t('training.delete')}
        onConfirm={() => remove.mutate(night.id, { onSuccess: () => toast(t('sleepLog.deleted')), onError: (error) => toast.error(error.message) })}
      />
    </li>
  )
}

/** Nights entered by hand in the last weeks, to check or remove them. Hidden when there are none. */
export function ManualNights() {
  const { t } = useI18n()
  const today = useTodayDate()
  const nights = useManualNights()
  if (!nights.data?.length) return null
  return (
    <section>
      <SectionLabel count={nights.data.length}>{t('sleepLog.list')}</SectionLabel>
      <ul className="divide-y divide-rule/60">
        {nights.data.map((n) => (
          <ManualRow key={n.id} night={n} today={today} />
        ))}
      </ul>
    </section>
  )
}
