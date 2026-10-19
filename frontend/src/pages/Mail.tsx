import { useState } from 'react'
import { toast } from 'sonner'

import { useDismissMail, useMailOverview, useMails, useMailToTask, useSyncMail } from '../api/mail'
import { useTodayDate } from '../api/tasks'
import type { Mail, MailOverview } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { clockTime, localDay, pill, relativeDay } from '../lib/format'
import { isImportant } from '../lib/mail'

const DAYS = 14

function MailItem({ mail, today }: { mail: Mail; today: string }) {
  const { t, locale } = useI18n()
  const toTask = useMailToTask()
  const dismiss = useDismissMail()
  const sender = mail.from_name ?? mail.from_addr
  const pending = mail.triage === 'pending'
  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 truncate">
          {!mail.seen && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-brass align-middle" aria-label={t('mail.unread')} />}
          <span className={mail.seen ? '' : 'font-semibold'} title={mail.from_addr}>
            {sender}
          </span>
        </p>
        <p className="shrink-0 font-mono text-[11px] text-muted">
          {t(`mail.account.${mail.account}` as MessageKey)} · {relativeDay(localDay(mail.received_at), today, t, locale)}{' '}
          {clockTime(mail.received_at, locale)}
        </p>
      </div>
      <p className="mt-0.5 font-medium">{mail.subject}</p>
      {mail.summary ? (
        <p className="mt-1 text-sm text-muted">{mail.summary}</p>
      ) : (
        <p className="mt-1 font-mono text-[11px] text-muted">
          {pending ? (mail.account === 'uni' ? t('mail.pendingLocal') : t('mail.pending')) : t('mail.noSummary')}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {mail.needs_action && <span className="rounded-full border border-brass px-2 py-0.5 text-[11px] text-brass">{t('mail.needsAction')}</span>}
        {mail.task_title && !mail.task_id && <span className="text-[13px]">→ {mail.task_title}</span>}
        <span className="ml-auto flex gap-1.5">
          {mail.task_id ? (
            <span className="font-mono text-[11px] text-muted">{t('mail.hasTask')}</span>
          ) : (
            <button
              type="button"
              disabled={toTask.isPending}
              onClick={() =>
                toTask.mutate(mail.id, {
                  onSuccess: (task) => toast(t('mail.toTaskDone', { title: task.title })),
                  onError: (error) => toast.error(error.message),
                })
              }
              className="rounded-md border border-brass px-2 py-0.5 text-sm text-brass hover:bg-brass/10 disabled:opacity-50"
            >
              {t('mail.toTask')}
            </button>
          )}
          <button
            type="button"
            disabled={dismiss.isPending}
            onClick={() => dismiss.mutate({ id: mail.id, dismissed: !mail.dismissed }, { onError: (error) => toast.error(error.message) })}
            className="rounded-md border border-rule px-2 py-0.5 text-sm text-muted hover:border-ink hover:text-ink disabled:opacity-50"
          >
            {mail.dismissed ? t('mail.restore') : t('mail.dismiss')}
          </button>
        </span>
      </div>
    </li>
  )
}

function Accounts({ overview, today }: { overview: MailOverview; today: string }) {
  const { t, locale } = useI18n()
  return (
    <ul className="mb-6 space-y-0.5 font-mono text-[11px] text-muted">
      {overview.accounts.map((a) => (
        <li key={a.account}>
          {t(`mail.account.${a.account}` as MessageKey)} · {t(`mail.triage.${a.triage}` as MessageKey)} ·{' '}
          {a.last_success_at
            ? t('mail.syncOk', { when: `${relativeDay(localDay(a.last_success_at), today, t, locale)} ${clockTime(a.last_success_at, locale)}` })
            : t('mail.syncNever')}
          {a.pending > 0 && ` · ${t('mail.pendingN', { n: a.pending })}`}
          {a.last_error && <span className="block text-signal">{t('mail.syncError', { message: a.last_error })}</span>}
        </li>
      ))}
    </ul>
  )
}

function Section({ label, mails, today, tone, collapsed }: { label: string; mails: Mail[]; today: string; tone?: 'signal'; collapsed?: boolean }) {
  if (mails.length === 0) return null
  const list = (
    <ul className="divide-y divide-rule/60">
      {mails.map((m) => (
        <MailItem key={m.id} mail={m} today={today} />
      ))}
    </ul>
  )
  if (collapsed) {
    return (
      <details>
        <summary className="cursor-pointer list-none">
          <SectionLabel count={mails.length}>{label}</SectionLabel>
        </summary>
        {list}
      </details>
    )
  }
  return (
    <section>
      <SectionLabel count={mails.length} tone={tone}>
        {label}
      </SectionLabel>
      {list}
    </section>
  )
}

export function MailPage() {
  const { t } = useI18n()
  const today = useTodayDate()
  const [account, setAccount] = useState<string | undefined>()
  const [dismissed, setDismissed] = useState(false)
  const overview = useMailOverview()
  const mails = useMails({ days: DAYS, account, dismissed })
  const sync = useSyncMail()

  const header = (
    <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('mail.title')}</h1>
      <button
        type="button"
        disabled={sync.isPending}
        onClick={() =>
          sync.mutate(undefined, {
            onSuccess: (result) => {
              const created = Object.values(result).reduce<number>((n, r) => n + (typeof r === 'object' && r && 'new' in r ? Number(r.new) : 0), 0)
              toast(t('mail.fetched', { n: created }))
            },
            onError: (error) => toast.error(error.message),
          })
        }
        className="rounded-md bg-brass px-3 py-2 text-sm font-medium text-brass-ink hover:opacity-90 disabled:opacity-50"
      >
        {sync.isPending ? t('mail.fetching') : t('mail.fetch')}
      </button>
    </header>
  )

  if (overview.error || mails.error) {
    return <>{header}<p className="text-signal">{t('mail.loadError', { message: (overview.error ?? mails.error)!.message })}</p></>
  }
  if (overview.isPending || mails.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  if (overview.data.accounts.length === 0) {
    return (
      <>
        {header}
        <p className="mt-4 max-w-md text-muted">{t('mail.empty')}</p>
      </>
    )
  }

  const list = mails.data
  const important = list.filter(isImportant)
  const low = list.filter((m) => !isImportant(m) && m.priority === 'low')
  const normal = list.filter((m) => !isImportant(m) && m.priority !== 'low')

  return (
    <>
      {header}
      <Accounts overview={overview.data} today={today} />

      <div className="mb-6 flex flex-wrap gap-1.5">
        <button type="button" className={pill(!account)} aria-pressed={!account} onClick={() => setAccount(undefined)}>
          {t('mail.all')}
        </button>
        {overview.data.accounts.map((a) => (
          <button key={a.account} type="button" className={pill(account === a.account)} aria-pressed={account === a.account} onClick={() => setAccount(a.account)}>
            {t(`mail.account.${a.account}` as MessageKey)}
          </button>
        ))}
        <button type="button" className={`${pill(dismissed)} ml-auto`} aria-pressed={dismissed} onClick={() => setDismissed(!dismissed)}>
          {t('mail.dismissedList')}
        </button>
      </div>

      {list.length === 0 && <p className="text-muted">{t('mail.nothing')}</p>}
      <div className="space-y-8">
        {dismissed ? (
          <Section label={t('mail.dismissedList')} mails={list} today={today} />
        ) : (
          <>
            <Section label={t('mail.important')} mails={important} today={today} tone="signal" />
            <Section label={t('mail.normal')} mails={normal} today={today} />
            <Section label={t('mail.low')} mails={low} today={today} collapsed />
          </>
        )}
        <p className="max-w-xl text-sm text-muted">{t('mail.hint')}</p>
      </div>
    </>
  )
}
