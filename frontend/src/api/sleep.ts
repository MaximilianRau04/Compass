import { useQuery } from '@tanstack/react-query'

import { api } from './client'
import type { DayHeartRate, HealthAnalysis, HealthSummary } from './types'

export function useHealthSummary(days = 30) {
  return useQuery({
    queryKey: ['sleep', 'summary', days],
    queryFn: () => api<HealthSummary>(`/sleep/summary?days=${days}`),
  })
}

export function useDayHeartRate(day?: string) {
  return useQuery({
    queryKey: ['sleep', 'heart-rate', day ?? 'today'],
    queryFn: () => api<DayHeartRate>(`/sleep/heart-rate${day ? `?day=${day}` : ''}`),
  })
}

export function useHealthAnalysis(days = 30) {
  return useQuery({ queryKey: ['sleep', 'analysis', days], queryFn: () => api<HealthAnalysis>(`/sleep/analysis?days=${days}`) })
}

export interface Bedtime {
  day: string
  event: { title: string; starts_at: string } | null
  wake_at?: string
  latest_bedtime?: string
  capped?: boolean
  sleep_need_minutes?: number
  fall_asleep_minutes?: number
}

export function useBedtime(enabled: boolean) {
  return useQuery({ queryKey: ['sleep', 'bedtime'], queryFn: () => api<Bedtime>('/sleep/bedtime'), enabled })
}
