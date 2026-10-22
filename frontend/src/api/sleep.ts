import { useQuery } from '@tanstack/react-query'

import { api } from './client'
import type { DayHeartRate, HealthSummary } from './types'

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
