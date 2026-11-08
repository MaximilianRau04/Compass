import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { useI18n } from '../i18n/context'
import { pill } from '../lib/format'
import { discardDraft } from '../lib/workout'
import { Active } from './workout/Active'
import { Start } from './workout/Start'
import { nowIso, useDraft } from './workout/hooks'

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
