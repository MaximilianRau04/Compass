import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { pollSignIn, useDismissMail, useMail, useMailContent, useMailOverview, useMails, useMailToTask, useSignOut, useStartSignIn, useSyncMail } from '../api/mail'
import { useTodayDate } from '../api/tasks'
import type { Mail, MailAccount, MailOverview, SignInStart } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { clockTime, localDay, pill, relativeDay } from '../lib/format'
import { accountName, isImportant } from '../lib/mail'
import { button, overlay, pageTitle } from '../lib/ui'

const DAYS = 14

function MailItem({ mail, today, local }: { mail: Mail; today: string; local: boolean }) {
  const { t, locale } = useI18n()
  const toTask = useMailToTask()
  const dismiss = useDismissMail()
  const sender = mail.from_name ?? mail.from_addr
  const pending = mail.triage === 'pending'
  const important = isImportant(mail)
  const [open, setOpen] = useState(false)
  const content = useMailContent(mail.id, open)
  return (
    <li className={['py-3', important ? '-ml-3 border-l-2 border-brass pl-2.5' : '', mail.priority === 'low' && !important ? 'opacity-60' : ''].join(' ')}>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Trigger asChild>
          <button type="button" className="block w-full min-w-0 rounded-md px-2 py-1 text-left transition-colors hover:bg-paper-raised focus-visible:outline-2 focus-visible:outline-brass">
            <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="min-w-0 truncate">
                {!mail.seen && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-brass align-middle" aria-label={t('mail.unread')} />}
                <span className={mail.seen ? '' : 'font-semibold'} title={mail.from_addr}>{sender}</span>
              </span>
              <span className="font-mono text-2xs text-muted">
                {accountName(mail.account)} · {relativeDay(localDay(mail.received_at), today, t, locale)}{' '}
                {clockTime(mail.received_at, locale)}
              </span>
            </span>
            <span className="mt-0.5 block break-words font-medium">{mail.subject}</span>
            {mail.summary ? (
              <span className="mt-1 block text-sm text-muted">{mail.summary}</span>
            ) : (
              <span className="mt-1 block font-mono text-2xs text-muted">
                {pending ? (local ? t('mail.pendingLocal') : t('mail.pending')) : t('mail.noSummary')}
              </span>
            )}
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className={overlay} />
          <Dialog.Content
            className="fixed inset-x-0 bottom-0 z-50 max-h-[92dvh] overflow-y-auto rounded-t-xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-lg sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[min(42rem,calc(100vw-2rem))] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl"
            aria-describedby={undefined}
          >
            <div className="flex items-start justify-between gap-3">
              <Dialog.Title className="min-w-0 break-words text-xl font-semibold leading-snug">{mail.subject}</Dialog.Title>
              <Dialog.Close className={button('quiet', 'sm')} aria-label={t('mail.close')}>×</Dialog.Close>
            </div>
            <dl className="mt-4 space-y-1 break-words text-sm">
              <div><dt className="inline font-semibold">{t('mail.from')}: </dt><dd className="inline">{mail.from_name ? `${mail.from_name} <${mail.from_addr}>` : mail.from_addr}</dd></div>
              {mail.account && <div><dt className="inline font-semibold">{t('mail.mailbox')}: </dt><dd className="inline">{mail.account}</dd></div>}
              <div><dt className="inline font-semibold">{t('mail.date')}: </dt><dd className="inline">{new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeStyle: 'short' }).format(new Date(mail.received_at))}</dd></div>
            </dl>
            <div className="mt-4 border-t border-rule pt-4 text-sm" aria-live="polite">
              {content.isPending && <p className="text-muted">{t('common.loading')}</p>}
              {content.error && <p role="alert" className="text-signal">{t('mail.contentError', { message: content.error.message })}</p>}
              {content.data && (
                <>
                  <div className="whitespace-pre-wrap break-words">{content.data.text || t('mail.emptyContent')}</div>
                  {content.data.truncated && <p className="mt-2 text-muted">{t('mail.truncated')}</p>}
                  {content.data.attachments.length > 0 && <p className="mt-2 break-words text-muted">{t('mail.attachments')}: {content.data.attachments.join(', ')}</p>}
                </>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {mail.needs_action && <span className="rounded-full border border-brass px-2 py-0.5 text-2xs text-brass">{t('mail.needsAction')}</span>}
        {mail.task_title && !mail.task_id && <span className="text-label">→ {mail.task_title}</span>}
        <span className="ml-auto flex gap-1.5">
          {mail.task_id ? (
            <span className="self-center font-mono text-2xs text-muted">✓ {t('mail.hasTask')}</span>
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

/** Device sign-in: the user enters the code at Microsoft, the page asks the server until it is
 * done. Compass never sees the Microsoft password. */
function SignInCode({ account, code, onEnd }: { account: string; code: SignInStart; onEnd: () => void }) {
  const { t } = useI18n()
  const sync = useSyncMail()
  useEffect(() => {
    let stopped = false
    const timer = window.setInterval(async () => {
      if (stopped) return
      if (Date.now() > Date.parse(code.expires_at)) {
        stopped = true
        toast.error(t('mail.signin.expired'))
        onEnd()
        return
      }
      try {
        const result = await pollSignIn(account)
        if (stopped || result.status === 'pending') return
        stopped = true
        if (result.status === 'done') {
          toast(t('mail.signin.done', { who: result.signed_in_as ?? accountName(account) }))
          sync.mutate()
        } else {
          toast.error(t('mail.signin.failed', { message: result.message ?? '' }))
        }
        onEnd()
      } catch (error) {
        stopped = true
        toast.error(t('mail.signin.failed', { message: (error as Error).message }))
        onEnd()
      }
    }, Math.max(code.interval, 3) * 1000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
    // Runs once per code; sync and t are stable enough for the few minutes it waits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, code])
  return (
    <div className="my-2 max-w-md rounded border border-brass/60 p-3 font-sans text-sm text-ink">
      <p>
        {t('mail.signin.step1')}{' '}
        <a href={code.verification_uri} target="_blank" rel="noreferrer" className="text-brass underline">
          {code.verification_uri.replace(/^https?:\/\//, '')}
        </a>
      </p>
      <p className="mt-1">{t('mail.signin.step2')}</p>
      <p className="mt-2 flex items-center gap-3">
        <span className="select-all font-mono text-lg tracking-widest">{code.user_code}</span>
        <button
          type="button"
          className={button('quiet', 'sm')}
          onClick={() => void navigator.clipboard?.writeText(code.user_code).then(() => toast(t('mail.signin.copied')))}
        >
          {t('mail.signin.copy')}
        </button>
      </p>
      <p className="mt-2 font-mono text-2xs text-muted">{t('mail.signin.waiting')}</p>
      <button type="button" className={`${button('quiet', 'sm')} mt-1`} onClick={onEnd}>
        {t('common.cancel')}
      </button>
    </div>
  )
}

function SignIn({ account }: { account: MailAccount }) {
  const { t } = useI18n()
  const start = useStartSignIn()
  const signOut = useSignOut()
  const [code, setCode] = useState<SignInStart | null>(null)
  const signedIn = account.signed_in === true
  if (code) return <SignInCode account={account.account} code={code} onEnd={() => setCode(null)} />
  return (
    <span className="block">
      {signedIn && t('mail.signin.as', { who: account.signed_in_as ?? '?' })}{' '}
      <button
        type="button"
        disabled={start.isPending}
        className={signedIn ? 'text-muted underline hover:text-ink' : `${button('secondary', 'sm')} mt-1 border-brass/60 text-brass hover:border-brass`}
        onClick={() => start.mutate(account.account, { onSuccess: setCode, onError: (error) => toast.error(error.message) })}
      >
        {signedIn ? t('mail.signin.again') : t('mail.signin.start')}
      </button>
      {signedIn && (
        <>
          {' · '}
          <button
            type="button"
            disabled={signOut.isPending}
            className="text-muted underline hover:text-ink"
            onClick={() => signOut.mutate(account.account, { onSuccess: () => toast(t('mail.signin.signedOut')), onError: (error) => toast.error(error.message) })}
          >
            {t('mail.signin.signOut')}
          </button>
        </>
      )}
    </span>
  )
}

function Accounts({ overview, today }: { overview: MailOverview; today: string }) {
  const { t, locale } = useI18n()
  return (
    <section className="mb-6" aria-label={t('mail.sources')}>
      <h2 className="mb-2 font-display text-lg font-semibold">{t('mail.sources')}</h2>
      <p className="mb-3 text-xs text-muted">{t('mail.sourceHint')}</p>
      <ul className="space-y-2 text-sm">
      {overview.accounts.map((a) => {
        const needsSignIn = a.auth !== 'password' && a.signed_in === false
        return (
          <li key={a.account} className="min-w-0 border-b border-rule/60 pb-2 last:border-0">
            <p className="min-w-0 break-words font-medium text-ink">{accountName(a.account)}</p>
            <p className="text-muted">
              {t(`mail.triage.${a.triage}` as MessageKey)} ·{' '}
              {a.last_success_at
                ? t('mail.syncOk', { when: `${relativeDay(localDay(a.last_success_at), today, t, locale)} ${clockTime(a.last_success_at, locale)}` })
                : t('mail.syncNever')}
              {a.pending > 0 && ` · ${t('mail.pendingN', { n: a.pending })}`}
            </p>
            {needsSignIn ? (
              <span className="block break-words text-signal">{a.signin_error ? t('mail.signin.error', { message: a.signin_error }) : t('mail.signin.needed')}</span>
            ) : (
              a.last_error && <span className="block break-words text-signal">{t('mail.syncError', { message: a.last_error })}</span>
            )}
            {a.auth !== 'password' && <SignIn account={a} />}
          </li>
        )
      })}
      </ul>
    </section>
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
  // A hit of the search arrives as ?id=: that mail stands on top, whatever its age or the filters.
  const [params, setParams] = useSearchParams()
  const foundId = Number(params.get('id')) || null
  const found = useMail(foundId)

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
              const failed = Object.values(result).filter((r) => typeof r === 'string').length
              toast(failed ? t('mail.fetchPartial', { n: failed }) : t('mail.fetched', { n: created }))
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
  const rest = shown.filter((m) => m.id !== found.data?.id)

  return (
    <>
      {header}
      <Accounts overview={overview.data} today={today} />

      <div className="mb-2 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className={pill(!dismissed && filter === f.key)} aria-pressed={!dismissed && filter === f.key} onClick={() => { setFilter(f.key); setDismissed(false) }}>
            {t(f.label)} <span className="font-mono text-2xs opacity-70">{dismissed ? '' : list.filter(f.test).length}</span>
          </button>
        ))}
        <button type="button" className={`${pill(dismissed)} ml-auto`} aria-pressed={dismissed} onClick={() => setDismissed(!dismissed)}>
          {t('mail.dismissedList')}
        </button>
      </div>
      <div className="mb-6 flex flex-wrap gap-x-3 gap-y-1 font-mono text-data">
        <button type="button" aria-pressed={!account} onClick={() => setAccount(undefined)} className={!account ? 'text-brass' : 'text-muted hover:text-ink'}>
          {t('mail.allAccounts')}
        </button>
        {overview.data.accounts.map((a) => (
          <button key={a.account} type="button" aria-pressed={account === a.account} onClick={() => setAccount(account === a.account ? undefined : a.account)} className={account === a.account ? 'text-brass' : 'text-muted hover:text-ink'}>
            {accountName(a.account)}
          </button>
        ))}
      </div>

      {foundId !== null && (
        <section className="mb-8">
          <div className="relative">
            <SectionLabel>{t('mail.found')}</SectionLabel>
            <button type="button" className="absolute top-0 right-0 font-mono text-2xs text-muted hover:text-ink" onClick={() => setParams({}, { replace: true })}>
              {t('mail.foundClose')}
            </button>
          </div>
          {found.data && (
            <ul>
              <MailItem mail={found.data} today={today} local={local.has(found.data.account)} />
            </ul>
          )}
          {found.isPending && <p className="font-mono text-sm text-muted">{t('common.loading')}</p>}
          {found.error && <p className="text-muted">{t('mail.foundGone')}</p>}
        </section>
      )}

      {rest.length === 0 && (
        <p className="text-muted">
          {dismissed ? t('mail.nothingDismissed') : filter !== 'all' ? t('mail.nothingFiltered') : t('mail.nothing')}
        </p>
      )}
      <div className="space-y-8">
        <ByDay mails={rest} today={today} local={local} />
        <p className="max-w-xl text-sm text-muted">{t('mail.hint')}</p>
      </div>
    </>
  )
}
