import { useState } from 'react'
import { toast } from 'sonner'

import { useDismissMail, useMailOverview, useMails, useMailToTask, useSyncMail } from '../api/mail'
import { useTodayDate } from '../api/tasks'
import type { Mail, MailOverview } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { clockTime, localDay, pill, relativeDay } from '../lib/format'
import { accountName, isImportant } from '../lib/mail'
import { button, pageTitle } from '../lib/ui'

const DAYS = 14

function MailItem({ mail, today, local }: { mail: Mail; today: string; local: boolean }) {
  const { t, locale } = useI18n()
  const toTask = useMailToTask()
  const dismiss = useDismissMail()
  const sender = mail.from_name ?? mail.from_addr
  const pending = mail.triage === 'pending'
  const important = isImportant(mail)
  return (
    <li className={['py-3', important ? '-ml-3 border-l-2 border-brass pl-2.5' : '', mail.priority === 'low' && !important ? 'opacity-60' : ''].join(' ')}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 truncate">
          {!mail.seen && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-brass align-middle" aria-label={t('mail.unread')} />}
          <span className={mail.seen ? '' : 'font-semibold'} title={mail.from_addr}>
            {sender}
          </span>
        </p>
        <p className="shrink-0 font-mono text-[11px] text-muted">
          {accountName(mail.account)} · {relativeDay(localDay(mail.received_at), today, t, locale)}{' '}
          {clockTime(mail.received_at, locale)}
        </p>
      </div>
      <p className="mt-0.5 font-medium">{mail.subject}</p>
      {mail.summary ? (
        <p className="mt-1 text-sm text-muted">{mail.summary}</p>
      ) : (
        <p className="mt-1 font-mono text-[11px] text-muted">
          {pending ? (local ? t('mail.pendingLocal') : t('mail.pending')) : t('mail.noSummary')}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {mail.needs_action && <span className="rounded-full border border-brass px-2 py-0.5 text-[11px] text-brass">{t('mail.needsAction')}</span>}
        {mail.task_title && !mail.task_id && <span className="text-[13px]">→ {mail.task_title}</span>}
        <span className="ml-auto flex gap-1.5">
          {mail.task_id ? (
            <span className="self-center font-mono text-[11px] text-muted">✓ {t('mail.hasTask')}</span>
          ) : (
            <button
              type="button"
              disabled={toTask.isPending}
              onClick={() =>
                toTask.mutate(mail.id, {
                  // The mail is handled now and leaves the list; the task carries it.
                  onSuccess: (task) => toast(t('mail.toTaskDone', { title: task.title })),
                  onError: (error) => toast.error(error.message),
                })
              }
              className={`${button('secondary', 'sm')} border-brass/60 text-brass hover:border-brass`}
            >
              {t('mail.toTask')}
            </button>
          )}
          <button
            type="button"
            disabled={dismiss.isPending}
            onClick={() =>
              dismiss.mutate(
                { id: mail.id, dismissed: !mail.dismissed },
                {
                  onSuccess: () =>
                    mail.dismissed
                      ? undefined
                      : toast(t('mail.dismissed'), { action: { label: t('sheet.undo'), onClick: () => dismiss.mutate({ id: mail.id, dismissed: false }) } }),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
            className={button('quiet', 'sm')}
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
          {accountName(a.account)} · {t(`mail.triage.${a.triage}` as MessageKey)} ·{' '}
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

type Filter = 'all' | 'unread' | 'important'

const FILTERS: { key: Filter; label: MessageKey; test: (m: Mail) => boolean }[] = [
  { key: 'all', label: 'mail.all', test: () => true },
  { key: 'unread', label: 'mail.unreadList', test: (m) => !m.seen },
  { key: 'important', label: 'mail.important', test: isImportant },
]

/** Mails newest first, one section per day. */
function ByDay({ mails, today, local }: { mails: Mail[]; today: string; local: Set<string> }) {
  const { t, locale } = useI18n()
  const days = new Map<string, Mail[]>()
  for (const mail of mails) {
    const day = localDay(mail.received_at)
    days.set(day, [...(days.get(day) ?? []), mail])
  }
  return (
    <>
      {[...days].map(([day, items]) => (
        <section key={day}>
          <SectionLabel count={items.length}>{relativeDay(day, today, t, locale)}</SectionLabel>
          <ul className="divide-y divide-rule/60">
            {items.map((m) => (
              <MailItem key={m.id} mail={m} today={today} local={local.has(m.account)} />
            ))}
          </ul>
        </section>
      ))}
    </>
  )
}

export function MailPage() {
  const { t } = useI18n()
  const today = useTodayDate()
  const [account, setAccount] = useState<string | undefined>()
  const [dismissed, setDismissed] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')
  const overview = useMailOverview()
  const mails = useMails({ days: DAYS, account, dismissed })
  const sync = useSyncMail()

  const header = (
    <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
      <h1 className={pageTitle}>{t('mail.title')}</h1>
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
        className={button('primary')}
      >
        {sync.isPending ? t('mail.fetching') : t('mail.fetch')}
      </button>
    </header>
  )

  if (overview.error || mails.error) {
    return <>{header}<p className="text-signal">{t('mail.loadError', { message: (overview.error ?? mails.error)!.message })}</p></>
  }
  if (overview.isPending || mails.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const local = new Set(overview.data.accounts.filter((a) => a.triage === 'local').map((a) => a.account))

  if (overview.data.accounts.length === 0) {
    return (
      <>
        {header}
        <p className="mt-4 max-w-md text-muted">{t('mail.empty')}</p>
      </>
    )
  }

  const list = mails.data
  const shown = dismissed ? list : list.filter(FILTERS.find((f) => f.key === filter)!.test)

  return (
    <>
      {header}
      <Accounts overview={overview.data} today={today} />

      <div className="mb-2 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className={pill(!dismissed && filter === f.key)} aria-pressed={!dismissed && filter === f.key} onClick={() => { setFilter(f.key); setDismissed(false) }}>
            {t(f.label)} <span className="font-mono text-[11px] opacity-70">{dismissed ? '' : list.filter(f.test).length}</span>
          </button>
        ))}
        <button type="button" className={`${pill(dismissed)} ml-auto`} aria-pressed={dismissed} onClick={() => setDismissed(!dismissed)}>
          {t('mail.dismissedList')}
        </button>
      </div>
      <div className="mb-6 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[12px]">
        <button type="button" aria-pressed={!account} onClick={() => setAccount(undefined)} className={!account ? 'text-brass' : 'text-muted hover:text-ink'}>
          {t('mail.allAccounts')}
        </button>
        {overview.data.accounts.map((a) => (
          <button key={a.account} type="button" aria-pressed={account === a.account} onClick={() => setAccount(account === a.account ? undefined : a.account)} className={account === a.account ? 'text-brass' : 'text-muted hover:text-ink'}>
            {accountName(a.account)}
          </button>
        ))}
      </div>

      {shown.length === 0 && <p className="text-muted">{t('mail.nothing')}</p>}
      <div className="space-y-8">
        <ByDay mails={shown} today={today} local={local} />
        <p className="max-w-xl text-sm text-muted">{t('mail.hint')}</p>
      </div>
    </>
  )
}
