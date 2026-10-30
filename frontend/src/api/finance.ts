import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, patch, post } from './client'

export interface BankConnection {
  id: number
  aspsp_name: string
  status: 'active' | 'expired'
  valid_until: string | null
  last_sync_at: string | null
  last_error: string | null
}

export interface FinanceStatus {
  configured: boolean
  connections: BankConnection[]
}

export interface Bank {
  name: string
  country: string
  logo: string | null
}

export interface FinanceMonth {
  month: string
  income: number
  spending: number
  saved: number
  by_category: Record<string, number>
  uncategorized: number
}

export interface RecurringPayment {
  name: string
  category: string | null
  amount: number
  interval: 'monthly' | 'quarterly' | 'yearly'
  monthly_cost: number
  last_date: string
  next_date: string
  count: number
}

export interface FinanceOverview {
  months: FinanceMonth[]
  budgets: Record<string, number>
  accounts: { id: number; name: string; iban: string | null; currency: string; balance: number | null; balance_at: string | null }[]
  cash: number
  depot: { date: string; value: number }[]
  depot_value: number | null
  invested: number
  net_worth: number
  recurring: RecurringPayment[]
  categories: string[]
  spending_categories: string[]
}

export interface BankTransaction {
  id: number
  account: string
  booking_date: string
  amount: number
  currency: string
  counterparty: string | null
  purpose: string | null
  category: string | null
  category_source: string | null
}

const invalidate = (qc: ReturnType<typeof useQueryClient>) => qc.invalidateQueries({ queryKey: ['finance'] })

export function useFinanceStatus() {
  return useQuery({ queryKey: ['finance', 'status'], queryFn: () => api<FinanceStatus>('/finance/status') })
}

export function useFinanceOverview(months = 6) {
  return useQuery({ queryKey: ['finance', 'overview', months], queryFn: () => api<FinanceOverview>(`/finance/overview?months=${months}`) })
}

export function useBanks(q: string) {
  return useQuery({
    queryKey: ['finance', 'banks', q],
    queryFn: () => api<Bank[]>(`/finance/banks?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
    staleTime: 3_600_000,
  })
}

export function useTransactions(uncategorized: boolean) {
  return useQuery({
    queryKey: ['finance', 'transactions', uncategorized],
    queryFn: () => api<BankTransaction[]>(`/finance/transactions?days=90${uncategorized ? '&uncategorized=true' : ''}`),
  })
}

export const startConnect = (name: string) => post<{ url: string }>('/finance/connect', { name })

export const finishConnect = (code: string, state: string) =>
  post<{ new_transactions: Record<string, number> }>('/finance/connect/finish', { code, state })

export function useSyncFinance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<{ new_transactions: Record<string, number> }>('/finance/sync'),
    onSettled: () => invalidate(qc),
  })
}

export function useCategorize() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, category, rule_pattern }: { id: number; category: string; rule_pattern?: string }) =>
      patch<{ rule_changed: number }>(`/finance/transactions/${id}`, { category, rule_pattern }),
    onSettled: () => invalidate(qc),
  })
}

export function useSetBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ category, amount }: { category: string; amount: number }) =>
      api(`/finance/budgets/${category}`, { method: 'PUT', body: JSON.stringify({ amount }) }),
    onSettled: () => invalidate(qc),
  })
}

export function useLogDepot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (value: number) => post('/finance/depot', { value }),
    onSettled: () => invalidate(qc),
  })
}
