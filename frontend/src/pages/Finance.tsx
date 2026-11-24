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
  useCreateSavingsGoal,
  useDeleteSavingsGoal,
  useFinanceForecast,
  useFinanceOverview,
  useFinanceStatus,
  useLogDepot,
  useSavingsGoals,
  useSetBudget,
  useSetSplits,
  useSyncFinance,
  useTransactions,
  useUpdateSavingsGoal,
} from '../api/finance'
import { useTodayDate } from '../api/tasks'
import { ColumnChart } from '../components/charts'
import { DataTable, Stat } from '../components/DataBlocks'
import { SectionLabel } from '../components/Layout'
import { type Translate, useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { daysBetween, parseAmount, parseDate, pill, relativeDay } from '../lib/format'
import { button, pageTitle } from '../lib/ui'

/** Transactions shown at first and added per click. */
const TX_PAGE = 30
const INPUT = 'rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono focus:border-brass focus:outline-none'
// The bank sends the browser back once per approval; StrictMode would run the effect twice.
const handledCodes = new Set<string>()

const categoryLabel = (t: Translate, category: string | null) =>
  category ? t(`fin.cat.${category}` as MessageKey) : t('fin.cat.none')

// Totals assume all accounts share one currency.
function useCurrency() {
  return useFinanceOverview(6).data?.accounts[0]?.currency ?? 'EUR'
}

function useCurrencySymbol() {
  const { locale } = useI18n()
  const parts = new Intl.NumberFormat(locale, { style: 'currency', currency: useCurrency() }).formatToParts(0)
  return parts.find((part) => part.type === 'currency')?.value ?? ''
}

function useMoney() {
  const { locale } = useI18n()
  const currency = useCurrency()
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
      <p className="font-mono text-2xs text-muted">{t('fin.connectHint')}</p>
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
    <div className="space-y-1 font-mono text-2xs text-muted">
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
          color="var(--chart)"
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
  const { t, locale } = useI18n()
  const currencySymbol = useCurrencySymbol()
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
          const amount = editing === c ? parseAmount(value, locale) : NaN
          const validBudget = value.trim() !== '' && Number.isFinite(amount) && amount >= 0 && amount <= 100000
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
                      if (!validBudget) return
                      setBudget.mutate({ category: c, amount }, {
                        onSuccess: () => setEditing(null),
                        onError: (err) => toast.error(err.message),
                      })
                    }}
                  >
                    <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder={currencySymbol} className={`${INPUT} w-24 py-0.5 text-xs`} />
                    <button type="submit" disabled={setBudget.isPending || !validBudget} className="relative text-xs text-brass before:absolute before:-inset-2 before:content-[''] disabled:opacity-40">{t('fin.save')}</button>
                  </form>
                ) : (
                  <button type="button" onClick={() => (setEditing(c), setValue(budget ? String(budget) : ''))} className="relative mt-0.5 font-mono text-2xs text-muted hover:text-ink before:absolute before:-inset-y-2 before:inset-x-0 before:content-['']">
                    {budget !== undefined ? t('fin.editBudget') : t('fin.setBudget')}
                  </button>
                ))}
            </li>
          )
        })}
      </ul>
      {month.uncategorized > 0 && <p className="mt-3 font-mono text-2xs text-muted">{t('fin.uncategorized', { n: month.uncategorized })}</p>}
    </section>
  )
}

/** The end of this month: spending so far plus what is still due, and the balance left. */
function Forecast() {
  const { t } = useI18n()
  const money = useMoney()
  const f = useFinanceForecast().data
  if (!f) return null
  return (
    <section>
      <SectionLabel>{t('fin.forecast')}</SectionLabel>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Stat label={t('fin.forecastSpending')} value={money(f.projected_spending)} note={t('fin.forecastSpent', { spent: money(f.spent) })} />
        <Stat label={t('fin.forecastDue')} value={money(f.recurring_due, 2)} note={f.due.map((r) => r.name).join(', ') || undefined} />
        <Stat label={t('fin.forecastCash')} value={money(f.projected_cash)} note={t('fin.forecastCashHint', { n: f.days_left, perDay: money(f.variable_per_day) })} />
      </div>
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
          <p className="mt-2 font-mono text-2xs text-muted">{t('fin.recurringTotal', { total: money(total, 2) })}</p>
          <ul className="mt-2 divide-y divide-rule">
            {data.recurring.map((r) => (
              <li key={`${r.name}-${r.amount}`} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate">{r.name}</span>
                  <span className="font-mono text-2xs text-muted">
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
  const currencySymbol = useCurrencySymbol()
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
          const v = parseAmount(value, locale)
          if (!value.trim() || !Number.isFinite(v)) return
          log.mutate(v, { onSuccess: () => (setValue(''), toast(t('fin.savedToast'))), onError: (err) => toast.error(err.message) })
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">{t('fin.depotToday')}</span>
          <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" placeholder={currencySymbol} className={`${INPUT} w-36`} />
        </label>
        <button type="submit" disabled={log.isPending || !value.trim()} className={button('primary')}>
          {t('fin.save')}
        </button>
      </form>
      <p className="mt-1 font-mono text-2xs text-muted">
        {last
          ? t('fin.depotLast', { value: money(last.value), day: parseDate(last.date).toLocaleDateString(locale) }) +
            (before ? ` · ${t('fin.depotChange', { change: money(last.value - before.value) })}` : '')
          : t('fin.depotHint')}
        {data.invested > 0 && ` · ${t('fin.invested', { value: money(data.invested) })}`}
      </p>
    </section>
  )
}

function SavingsGoals() {
  const { t, locale } = useI18n()
  const money = useMoney()
  const goals = useSavingsGoals()
  const create = useCreateSavingsGoal()
  const update = useUpdateSavingsGoal()
  const remove = useDeleteSavingsGoal()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [target, setTarget] = useState('')
  const [current, setCurrent] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

  const list = goals.data ?? []
  return (
    <section>
      <div className="flex items-baseline justify-between gap-2">
        <SectionLabel>{t('fin.goals')}</SectionLabel>
        <button type="button" onClick={() => setAdding(!adding)} className="font-mono text-2xs text-brass hover:underline">
          {adding ? t('common.cancel') : `+ ${t('fin.goalAdd')}`}
        </button>
      </div>
      {adding && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-rule bg-paper-raised p-3"
          onSubmit={(e) => {
            e.preventDefault()
            const targetAmount = parseAmount(target, locale)
            const currentAmount = current.trim() ? parseAmount(current, locale) : 0
            if (!name.trim() || !Number.isFinite(targetAmount) || targetAmount <= 0 || !Number.isFinite(currentAmount) || currentAmount < 0) return
            create.mutate(
              { name: name.trim(), target_amount: targetAmount, current_amount: currentAmount, target_date: targetDate || null },
              {
                onSuccess: () => {
                  setName('')
                  setTarget('')
                  setCurrent('')
                  setTargetDate('')
                  setAdding(false)
                  toast(t('fin.goalSaved'))
                },
                onError: (err) => toast.error(err.message),
              },
            )
          }}
        >
          <label className="min-w-36 flex-1 text-sm">
            <span className="mb-1 block text-xs text-muted">{t('fin.goalName')}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required className={`${INPUT} w-full font-sans`} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">{t('fin.goalTarget')}</span>
            <input value={target} onChange={(e) => setTarget(e.target.value)} inputMode="decimal" required className={`${INPUT} w-28`} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">{t('fin.goalCurrent')}</span>
            <input value={current} onChange={(e) => setCurrent(e.target.value)} inputMode="decimal" placeholder="0" className={`${INPUT} w-28`} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">{t('fin.goalDate')}</span>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className={`${INPUT} w-36`} />
          </label>
          <button type="submit" disabled={create.isPending || !name.trim() || !target.trim()} className={button('primary')}>
            {t('fin.save')}
          </button>
        </form>
      )}
      {!adding && list.length === 0 && <p className="mt-2 text-sm text-muted">{t('fin.goalEmpty')}</p>}
      {list.length > 0 && (
        <ul className="mt-3 space-y-3">
          {list.map((g) => {
            const pct = g.target_amount > 0 ? Math.min(100, Math.round((g.current_amount / g.target_amount) * 100)) : 0
            return (
              <li key={g.id} className="rounded-lg border border-rule bg-paper-raised p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <span className="font-medium">{g.name}</span>
                    {g.target_date && (
                      <span className="ml-2 font-mono text-2xs text-muted">
                        {parseDate(g.target_date).toLocaleDateString(locale)}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 font-mono text-xs">
                    <span className="tabular-nums">
                      {money(g.current_amount)} / {money(g.target_amount)} ({pct} %)
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(editing === g.id ? null : g.id)
                        setEditValue(String(g.current_amount))
                      }}
                      className="text-brass hover:underline"
                    >
                      {t('fin.goalCurrent')}
                    </button>
                    <button
                      type="button"
                      onClick={() => remove.mutate(g.id, { onError: (err) => toast.error(err.message) })}
                      className="text-muted hover:text-signal"
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-rule">
                  <div className="h-full rounded-full bg-chart" style={{ width: `${pct}%` }} />
                </div>
                {editing === g.id && (
                  <form
                    className="mt-2 flex items-center gap-2"
                    onSubmit={(e) => {
                      e.preventDefault()
                      const val = parseAmount(editValue, locale)
                      if (!Number.isFinite(val) || val < 0) return
                      update.mutate(
                        { id: g.id, current_amount: val },
                        {
                          onSuccess: () => {
                            setEditing(null)
                            toast(t('fin.goalSaved'))
                          },
                          onError: (err) => toast.error(err.message),
                        },
                      )
                    }}
                  >
                    <input value={editValue} onChange={(e) => setEditValue(e.target.value)} inputMode="decimal" className={`${INPUT} w-28 text-xs`} />
                    <button type="submit" disabled={update.isPending} className={button('primary')}>
                      {t('fin.save')}
                    </button>
                  </form>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function TransactionRow({ tx, categories }: { tx: BankTransaction; categories: string[] }) {
  const { t, locale } = useI18n()
  const today = useTodayDate()
  const money = useMoney()
  const categorize = useCategorize()
  const setSplits = useSetSplits()
  const [splitting, setSplitting] = useState(false)
  const [rows, setRows] = useState<{ category: string; amount: string }[]>([])
  const party = tx.counterparty ?? ''
  const remember = party.length >= 3 && !/paypal/i.test(party)
  const absAmount = Math.abs(tx.amount)

  const openSplit = () => {
    if (splitting) {
      setSplitting(false)
      return
    }
    if (tx.splits.length >= 2) {
      setRows(tx.splits.map((s) => ({ category: s.category, amount: String(s.amount) })))
    } else {
      const half = Math.round((absAmount / 2) * 100) / 100
      const rest = Math.round((absAmount - half) * 100) / 100
      setRows([
        { category: tx.category ?? categories[0] ?? 'other', amount: String(half) },
        { category: categories.find((c) => c !== tx.category) ?? categories[0] ?? 'other', amount: String(rest) },
      ])
    }
    setSplitting(true)
  }

  const parsedTotal = rows.reduce((sum, r) => {
    const v = parseAmount(r.amount, locale)
    return sum + (Number.isFinite(v) && v > 0 ? v : 0)
  }, 0)
  const remaining = Math.round((absAmount - parsedTotal) * 100) / 100

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
    <li className="py-2 text-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0 flex-1">
          <span className="block truncate">{party || tx.purpose || '–'}</span>
          <span className="block truncate font-mono text-2xs text-muted">
            {relativeDay(tx.booking_date, today, t, locale)}
            {tx.purpose && party ? ` · ${tx.purpose}` : ''}
          </span>
          {tx.splits.length > 0 && (
            <span className="mt-1 flex flex-wrap gap-1.5 font-mono text-2xs text-muted">
              {tx.splits.map((s) => (
                <span key={s.id} className="rounded border border-rule px-1.5 py-0.5">
                  {categoryLabel(t, s.category)} {money(s.amount, 2)}
                </span>
              ))}
            </span>
          )}
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className={`font-mono tabular-nums ${tx.amount > 0 ? 'text-chart' : ''}`}>{money(tx.amount, 2)}</span>
          <div className="flex items-center gap-1.5">
            {tx.splits.length === 0 && (
              <select
                value={tx.category ?? ''}
                onChange={(e) => choose(e.target.value)}
                aria-label={t('fin.category')}
                className={`rounded border border-rule bg-paper-raised px-1 py-1.5 text-xs sm:py-0.5 ${tx.category ? 'text-muted' : 'text-brass'}`}
              >
                {!tx.category && <option value="">{t('fin.cat.none')}</option>}
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(t, c)}
                  </option>
                ))}
              </select>
            )}
            <button type="button" onClick={openSplit} className="font-mono text-2xs text-muted hover:text-ink">
              {t('fin.split')}
            </button>
          </div>
        </span>
      </div>
      {splitting && (
        <form
          className="mt-2 space-y-2 rounded-md border border-rule bg-paper-raised p-2.5"
          onSubmit={(e) => {
            e.preventDefault()
            const payload = rows.map((r) => ({ category: r.category, amount: parseAmount(r.amount, locale) }))
            if (payload.some((p) => !Number.isFinite(p.amount) || p.amount <= 0)) return
            setSplits.mutate(
              { id: tx.id, splits: payload },
              {
                onSuccess: () => {
                  setSplitting(false)
                  toast(t('fin.splitSaved'))
                },
                onError: (err) => toast.error(err.message),
              },
            )
          }}
        >
          {rows.map((row, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <select
                value={row.category}
                onChange={(e) => setRows(rows.map((r, i) => (i === idx ? { ...r, category: e.target.value } : r)))}
                className="rounded border border-rule bg-paper px-1.5 py-1 text-xs"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(t, c)}
                  </option>
                ))}
              </select>
              <input
                value={row.amount}
                onChange={(e) => setRows(rows.map((r, i) => (i === idx ? { ...r, amount: e.target.value } : r)))}
                inputMode="decimal"
                className={`${INPUT} w-24 py-1 text-xs`}
              />
              {rows.length > 2 && (
                <button type="button" onClick={() => setRows(rows.filter((_, i) => i !== idx))} className="text-muted hover:text-signal">
                  ×
                </button>
              )}
            </div>
          ))}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setRows([...rows, { category: categories[0] ?? 'other', amount: remaining > 0 ? String(remaining) : '' }])}
                className="font-mono text-2xs text-brass hover:underline"
              >
                + {t('fin.splitAdd')}
              </button>
              <span className={`font-mono text-2xs ${Math.abs(remaining) <= 0.01 ? 'text-muted' : 'text-signal'}`}>
                {t('fin.splitRemaining', { value: money(remaining, 2) })}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {tx.splits.length > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    setSplits.mutate(
                      { id: tx.id, splits: [] },
                      {
                        onSuccess: () => {
                          setSplitting(false)
                          toast(t('fin.splitSaved'))
                        },
                        onError: (err) => toast.error(err.message),
                      },
                    )
                  }
                  className="font-mono text-2xs text-muted hover:text-signal"
                >
                  {t('fin.splitClear')}
                </button>
              )}
              <button type="submit" disabled={setSplits.isPending || Math.abs(remaining) > 0.01} className={button('primary')}>
                {t('fin.save')}
              </button>
            </div>
          </div>
        </form>
      )}
    </li>
  )
}

function Transactions({ categories }: { categories: string[] }) {
  const { t } = useI18n()
  const [unsorted, setUnsorted] = useState(false)
  const [shown, setShown] = useState(TX_PAGE)
  const list = useTransactions(unsorted)
  const all = list.data ?? []
  // The unsorted ones are a to-do list, so they all show at once; everything else in pages.
  const visible = unsorted ? all : all.slice(0, shown)
  const pick = (value: boolean) => {
    setUnsorted(value)
    setShown(TX_PAGE)
  }
  return (
    <section>
      <SectionLabel>{t('fin.transactions')}</SectionLabel>
      <div className="mt-3 flex gap-2">
        <button type="button" className={pill(!unsorted)} onClick={() => pick(false)}>
          {t('fin.all')}
        </button>
        <button type="button" className={pill(unsorted)} onClick={() => pick(true)}>
          {t('fin.cat.none')}
        </button>
      </div>
      {list.isPending && <p className="mt-3 font-mono text-sm text-muted">{t('common.loading')}</p>}
      {list.data && !list.data.length && <p className="mt-3 text-sm text-muted">{t('fin.noTransactions')}</p>}
      <ul className="mt-2 divide-y divide-rule">
        {visible.map((tx) => (
          <TransactionRow key={tx.id} tx={tx} categories={categories} />
        ))}
      </ul>
      {visible.length < all.length && (
        <button type="button" onClick={() => setShown(shown + TX_PAGE)} className={`mt-3 w-full ${button('secondary')}`}>
          {t('common.more', { n: Math.min(TX_PAGE, all.length - visible.length) })}
        </button>
      )}
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
      <h1 className={pageTitle}>{t('fin.title')}</h1>
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
          className={button('secondary')}
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
        {data.accounts.length > 0 && <Forecast />}
        {data.accounts.length > 0 && <Months data={data} />}
        {data.accounts.length > 0 && <Categories data={data} />}
        {data.accounts.length > 0 && <Recurring data={data} />}
        <Depot data={data} />
        <SavingsGoals />
        {data.accounts.length > 0 && <Transactions categories={data.categories} />}
      </div>
    </>
  )
}
