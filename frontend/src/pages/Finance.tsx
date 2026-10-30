import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import {
  type BankConnection,
  type BankTransaction,
  type FinanceOverview,
  finishConnect,
  startConnect,
  useBanks,
  useCategorize,
  useFinanceOverview,
  useFinanceStatus,
  useLogDepot,
  useSetBudget,
  useSyncFinance,
  useTransactions,
} from '../api/finance'
import { useTodayDate } from '../api/tasks'
import { ColumnChart } from '../components/charts'
import { DataTable, Stat } from '../components/DataBlocks'
import { SectionLabel } from '../components/Layout'
import { type Translate, useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { daysBetween, parseDate, pill, relativeDay } from '../lib/format'

const INPUT = 'rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono focus:border-brass focus:outline-none'
// The bank sends the browser back once per approval; StrictMode would run the effect twice.
const handledCodes = new Set<string>()

const categoryLabel = (t: Translate, category: string | null) =>
  category ? t(`fin.cat.${category}` as MessageKey) : t('fin.cat.none')

function useMoney() {
  const { locale } = useI18n()
  // Totals assume all accounts share one currency.
  const currency = useFinanceOverview(6).data?.accounts[0]?.currency ?? 'EUR'
  return (value: number, digits = 0) =>
    new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}

/** Finish an approval when the bank redirected back to /finance?code=…&state=…. */
function useConnectCallback() {
  const { t } = useI18n()
  const [params, setParams] = useSearchParams()
  const code = params.get('code')
  const state = params.get('state')
  const error = params.get('error')
  const qc = useQueryClient()
  useEffect(() => {
    if (error) {
      toast.error(t('fin.connectFailed', { message: params.get('error_description') ?? error }))
      setParams({}, { replace: true })
      return
    }
    if (!code || !state || handledCodes.has(code)) return
    handledCodes.add(code)
    finishConnect(code, state).then(
      (r) => {
        const n = Object.values(r.new_transactions).reduce((a, b) => a + b, 0)
        toast(t('fin.connected', { n }))
        qc.invalidateQueries({ queryKey: ['finance'] })
      },
      (e: Error) => toast.error(t('fin.connectFailed', { message: e.message })),
    )
    setParams({}, { replace: true })
  }, [code, state, error, params, setParams, qc, t])
}

function BankPicker({ suggested }: { suggested?: string }) {
  const { t } = useI18n()
  const [q, setQ] = useState(suggested ?? '')
  const banks = useBanks(q)
  const [busy, setBusy] = useState(false)
  const go = (name: string) => {
    setBusy(true)
    startConnect(name).then(
      (r) => window.location.assign(r.url),
      (e: Error) => (setBusy(false), toast.error(e.message)),
    )
  }
  return (
    <div className="space-y-2">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('fin.searchBank')} className={`${INPUT} w-full max-w-sm font-sans`} />
      {banks.error && <p className="text-sm text-signal">{banks.error.message}</p>}
      <ul className="max-w-sm divide-y divide-rule rounded-md border border-rule bg-paper-raised">
        {(banks.data ?? []).map((b) => (
          <li key={b.name}>
            <button type="button" disabled={busy} onClick={() => go(b.name)} className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-paper disabled:opacity-50">
              {b.logo && <img src={b.logo} alt="" className="h-5 w-5 object-contain" />}
              {b.name}
            </button>
          </li>
        ))}
      </ul>
      <p className="font-mono text-[11px] text-muted">{t('fin.connectHint')}</p>
    </div>
  )
}

function Connections({ connections }: { connections: BankConnection[] }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const [picking, setPicking] = useState(false)
  const active = connections.filter((c) => c.status === 'active')
  if (!active.length) {
    return (
      <section>
        <SectionLabel>{t('fin.connect')}</SectionLabel>
        <div className="mt-3 space-y-3">
          {connections.some((c) => c.status === 'expired') && <p className="text-sm text-signal">{t('fin.expired')}</p>}
          <p className="max-w-lg text-sm text-muted">{t('fin.connectIntro')}</p>
          <BankPicker suggested={connections[0]?.aspsp_name} />
        </div>
      </section>
    )
  }
  return (
    <div className="space-y-1 font-mono text-[11px] text-muted">
      {active.map((c) => {
        const until = c.valid_until?.slice(0, 10)
        const left = until ? daysBetween(today, until) : null
        return (
          <p key={c.id} className={left !== null && left <= 7 ? 'text-signal' : ''}>
            {t('fin.connection', {
              bank: c.aspsp_name,
              until: until ? parseDate(until).toLocaleDateString(locale) : '–',
              synced: c.last_sync_at ? new Date(c.last_sync_at).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : '–',
            })}
            {c.last_error && ` · ${c.last_error}`}
            {left !== null && left <= 7 && (
              <button type="button" onClick={() => setPicking(true)} className="ml-2 underline">
                {t('fin.renew')}
              </button>
            )}
          </p>
        )
      })}
      {picking && <BankPicker suggested={active[0].aspsp_name} />}
    </div>
  )
}

function Months({ data }: { data: FinanceOverview }) {
  const { t, locale } = useI18n()
  const money = useMoney()
  const label = (m: string) => parseDate(`${m}-01`).toLocaleDateString(locale, { month: 'short' })
  const bars = data.months.map((m) => ({ key: m.month, value: m.spending, label: label(m.month) }))
  return (
    <section>
      <SectionLabel>{t('fin.months')}</SectionLabel>
      <div className="mt-3">
        <ColumnChart
          data={bars}
          ariaLabel={t('fin.months')}
          format={(v) => money(v)}
          tooltip={(d) => {
            const m = data.months.find((x) => x.month === d.key)!
            return (
              <>
                <p className="font-medium">{parseDate(`${m.month}-01`).toLocaleDateString(locale, { month: 'long', year: 'numeric' })}</p>
                <p>{t('fin.spending')}: {money(m.spending)}</p>
                <p>{t('fin.income')}: {money(m.income)}</p>
                <p>{t('fin.saved')}: {money(m.saved)}</p>
              </>
            )
          }}
        />
      </div>
      <DataTable head={[t('fin.month'), t('fin.spending')]} rows={data.months.map((m) => [label(m.month), money(m.spending)])} />
    </section>
  )
}

function Categories({ data }: { data: FinanceOverview }) {
  const { t } = useI18n()
  const money = useMoney()
  const setBudget = useSetBudget()
  const [editing, setEditing] = useState<string | null>(null)
  const [value, setValue] = useState('')
  const month = data.months[data.months.length - 1]
  const cats = new Set([...Object.keys(month.by_category), ...Object.keys(data.budgets)])
  const rows = [...cats]
    .map((c) => ({ c, spent: month.by_category[c] ?? 0, budget: data.budgets[c] }))
    .sort((a, b) => b.spent - a.spent)
  const top = Math.max(...rows.map((r) => Math.max(r.spent, r.budget ?? 0)), 1)
  return (
    <section>
      <SectionLabel>{t('fin.categories')}</SectionLabel>
      {!rows.length && <p className="mt-3 text-sm text-muted">{t('fin.noSpending')}</p>}
      <ul className="mt-3 space-y-2.5">
        {rows.map(({ c, spent, budget }) => {
          const over = budget !== undefined && spent > budget
          return (
            <li key={c} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span>{categoryLabel(t, c === 'uncategorized' ? null : c)}</span>
                <span className={`font-mono tabular-nums ${over ? 'text-signal' : ''}`}>
                  {money(spent)}
                  {budget !== undefined && <span className="text-muted"> / {money(budget)}</span>}
                </span>
              </div>
              <div className="relative mt-1 h-2 rounded-full bg-rule/60">
                <div className={`h-2 rounded-full ${over ? 'bg-signal' : 'bg-chart'}`} style={{ width: `${(spent / top) * 100}%` }} />
                {budget !== undefined && <div className="absolute top-[-2px] h-3 w-0.5 bg-ink" style={{ left: `${(budget / top) * 100}%` }} />}
              </div>
              {data.spending_categories.includes(c) &&
                (editing === c ? (
                  <form
                    className="mt-1 flex gap-2"
                    onSubmit={(e) => {
                      e.preventDefault()
                      setBudget.mutate({ category: c, amount: Number(value.replace(',', '.')) || 0 }, { onError: (err) => toast.error(err.message) })
                      setEditing(null)
                    }}
                  >
                    <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder="€" className={`${INPUT} w-24 py-0.5 text-xs`} />
                    <button type="submit" className="text-xs text-brass">{t('fin.save')}</button>
                  </form>
                ) : (
                  <button type="button" onClick={() => (setEditing(c), setValue(budget ? String(budget) : ''))} className="mt-0.5 font-mono text-[11px] text-muted hover:text-ink">
                    {budget !== undefined ? t('fin.editBudget') : t('fin.setBudget')}
                  </button>
                ))}
            </li>
          )
        })}
      </ul>
      {month.uncategorized > 0 && <p className="mt-3 font-mono text-[11px] text-muted">{t('fin.uncategorized', { n: month.uncategorized })}</p>}
    </section>
  )
}

function Recurring({ data }: { data: FinanceOverview }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const money = useMoney()
  const total = data.recurring.reduce((a, r) => a + r.monthly_cost, 0)
  return (
    <section>
      <SectionLabel count={data.recurring.length}>{t('fin.recurring')}</SectionLabel>
      {!data.recurring.length ? (
        <p className="mt-3 text-sm text-muted">{t('fin.noRecurring')}</p>
      ) : (
        <>
          <p className="mt-2 font-mono text-[11px] text-muted">{t('fin.recurringTotal', { total: money(total, 2) })}</p>
          <ul className="mt-2 divide-y divide-rule">
            {data.recurring.map((r) => (
              <li key={`${r.name}-${r.amount}`} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate">{r.name}</span>
                  <span className="font-mono text-[11px] text-muted">
                    {t(`fin.interval.${r.interval}` as MessageKey)} · {t('fin.next', { day: relativeDay(r.next_date, today, t, locale) })}
                  </span>
                </span>
                <span className="font-mono tabular-nums">{money(r.amount, 2)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function Depot({ data }: { data: FinanceOverview }) {
  const { t, locale } = useI18n()
  const money = useMoney()
  const log = useLogDepot()
  const [value, setValue] = useState('')
  const last = data.depot[data.depot.length - 1]
  const before = data.depot[data.depot.length - 2]
  return (
    <section>
      <SectionLabel>{t('fin.depot')}</SectionLabel>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          // German input: dots group thousands, the comma is the decimal point.
          const v = Number(value.includes(',') ? value.replace(/\./g, '').replace(',', '.') : value)
          if (!value.trim() || !Number.isFinite(v)) return
          log.mutate(v, { onSuccess: () => (setValue(''), toast(t('fin.savedToast'))), onError: (err) => toast.error(err.message) })
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">{t('fin.depotToday')}</span>
          <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder="€" className={`${INPUT} w-36`} />
        </label>
        <button type="submit" disabled={log.isPending || !value.trim()} className="rounded-md bg-brass px-3 py-1.5 text-sm font-medium text-brass-ink disabled:opacity-40">
          {t('fin.save')}
        </button>
      </form>
      <p className="mt-1 font-mono text-[11px] text-muted">
        {last
          ? t('fin.depotLast', { value: money(last.value), day: parseDate(last.date).toLocaleDateString(locale) }) +
            (before ? ` · ${t('fin.depotChange', { change: money(last.value - before.value) })}` : '')
          : t('fin.depotHint')}
        {data.invested > 0 && ` · ${t('fin.invested', { value: money(data.invested) })}`}
      </p>
    </section>
  )
}

function TransactionRow({ tx, categories }: { tx: BankTransaction; categories: string[] }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const money = useMoney()
  const categorize = useCategorize()
  const party = tx.counterparty ?? ''
  const remember = party.length >= 3 && !/paypal/i.test(party)
  const choose = (category: string) =>
    categorize.mutate(
      { id: tx.id, category },
      {
        onError: (err) => toast.error(err.message),
        onSuccess: () => {
          if (!remember) return
          toast(t('fin.categorized', { category: categoryLabel(t, category) }), {
            action: {
              label: t('fin.always', { party: party.slice(0, 24) }),
              onClick: () =>
                categorize.mutate(
                  { id: tx.id, category, rule_pattern: party.toLowerCase() },
                  { onSuccess: (r) => toast(t('fin.ruleSaved', { n: r.rule_changed })), onError: (err) => toast.error(err.message) },
                ),
            },
          })
        },
      },
    )
  return (
    <li className="flex items-start justify-between gap-3 py-2 text-sm">
      <span className="min-w-0 flex-1">
        <span className="block truncate">{party || tx.purpose || '–'}</span>
        <span className="block truncate font-mono text-[11px] text-muted">
          {relativeDay(tx.booking_date, today, t, locale)}
          {tx.purpose && party ? ` · ${tx.purpose}` : ''}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <span className={`font-mono tabular-nums ${tx.amount > 0 ? 'text-chart' : ''}`}>{money(tx.amount, 2)}</span>
        <select
          value={tx.category ?? ''}
          onChange={(e) => choose(e.target.value)}
          aria-label={t('fin.category')}
          className={`rounded border border-rule bg-paper-raised px-1 py-0.5 text-xs ${tx.category ? 'text-muted' : 'text-brass'}`}
        >
          {!tx.category && <option value="">{t('fin.cat.none')}</option>}
          {categories.map((c) => (
            <option key={c} value={c}>
              {categoryLabel(t, c)}
            </option>
          ))}
        </select>
      </span>
    </li>
  )
}

function Transactions({ categories }: { categories: string[] }) {
  const { t } = useI18n()
  const [unsorted, setUnsorted] = useState(false)
  const list = useTransactions(unsorted)
  return (
    <section>
      <SectionLabel>{t('fin.transactions')}</SectionLabel>
      <div className="mt-3 flex gap-2">
        <button type="button" className={pill(!unsorted)} onClick={() => setUnsorted(false)}>
          {t('fin.all')}
        </button>
        <button type="button" className={pill(unsorted)} onClick={() => setUnsorted(true)}>
          {t('fin.cat.none')}
        </button>
      </div>
      {list.isPending && <p className="mt-3 font-mono text-sm text-muted">{t('common.loading')}</p>}
      {list.data && !list.data.length && <p className="mt-3 text-sm text-muted">{t('fin.noTransactions')}</p>}
      <ul className="mt-2 divide-y divide-rule">
        {list.data?.map((tx) => (
          <TransactionRow key={tx.id} tx={tx} categories={categories} />
        ))}
      </ul>
    </section>
  )
}

export function FinancePage() {
  const { t } = useI18n()
  const money = useMoney()
  useConnectCallback()
  const status = useFinanceStatus()
  const overview = useFinanceOverview(6)
  const sync = useSyncFinance()

  const connected = status.data?.connections.some((c) => c.status === 'active')
  const header = (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('fin.title')}</h1>
      {connected && (
        <button
          type="button"
          disabled={sync.isPending}
          onClick={() =>
            sync.mutate(undefined, {
              onSuccess: (r) => toast(t('fin.synced', { n: Object.values(r.new_transactions).reduce((a, b) => a + b, 0) })),
              onError: (err) => toast.error(err.message),
            })
          }
          className="rounded-md border border-brass px-3 py-1.5 text-sm text-brass hover:bg-brass/10 disabled:opacity-50"
        >
          {sync.isPending ? t('fin.syncing') : t('fin.sync')}
        </button>
      )}
    </header>
  )

  if (status.error || overview.error) return <>{header}<p className="text-signal">{(status.error ?? overview.error)!.message}</p></>
  if (status.isPending || overview.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const data = overview.data
  const month = data.months[data.months.length - 1]
  const previous = data.months[data.months.length - 2]

  return (
    <>
      {header}
      <div className="space-y-10">
        {status.data.configured ? <Connections connections={status.data.connections} /> : <p className="max-w-lg text-sm text-muted">{t('fin.notConfigured')}</p>}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label={t('fin.netWorth')} value={money(data.net_worth)} />
          <Stat label={t('fin.cash')} value={money(data.cash)} note={data.accounts.map((a) => a.name).join(', ') || undefined} />
          <Stat label={t('fin.depot')} value={data.depot_value !== null ? money(data.depot_value) : '–'} note={data.depot.length ? undefined : t('fin.depotMissing')} />
          <Stat
            label={t('fin.spendingMonth')}
            value={money(month.spending)}
            note={previous ? t('fin.previousMonth', { value: money(previous.spending) }) : undefined}
          />
        </div>
        {data.accounts.length > 0 && <Months data={data} />}
        {data.accounts.length > 0 && <Categories data={data} />}
        {data.accounts.length > 0 && <Recurring data={data} />}
        <Depot data={data} />
        {data.accounts.length > 0 && <Transactions categories={data.categories} />}
      </div>
    </>
  )
}
