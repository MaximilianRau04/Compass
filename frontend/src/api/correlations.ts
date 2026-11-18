import { useQuery } from '@tanstack/react-query'

import { api } from './client'

export interface Correlation {
  x: string
  y: string
  /** Days between x and y */
  lag: number
  /** Days with both values */
  n: number
  /** Pearson's r, null below 10 days */
  r: number | null
  points: { date: string; x: number; y: number }[]
}

export function useCorrelations(days: number) {
  return useQuery({ queryKey: ['correlations', 'list', days], queryFn: () => api<Correlation[]>(`/correlations?days=${days}`) })
}

export function useCorrelation(x: string, y: string, lag: number, days: number) {
  const params = new URLSearchParams({ x, y, lag: String(lag), days: String(days) })
  return useQuery({
    queryKey: ['correlations', 'pair', x, y, lag, days],
    queryFn: () => api<Correlation>(`/correlations/pair?${params}`),
  })
}
