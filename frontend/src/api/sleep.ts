import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, del, post } from './client'
import type { DayHeartRate, HealthAnalysis, HealthSummary, SleepNight } from './types'

export type ReadinessReason = 'short_sleep' | 'resting_up' | 'hrv_down' | 'high_load'

export interface Readiness {
  date: string
  /** 0 to 100, null without last night or a resting heart rate */
  score: number | null
  level: 'good' | 'moderate' | 'low' | null
  reasons: ReadinessReason[]
  asleep_minutes: number | null
  resting_hr: number | null
  resting_median: number | null
  hrv: number | null
  hrv_median: number | null
}

export function useReadiness() {
  return useQuery({ queryKey: ['sleep', 'readiness'], queryFn: () => api<Readiness>('/sleep/readiness') })
}

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

export function useManualNights() {
  return useQuery({ queryKey: ['sleep', 'manual'], queryFn: () => api<SleepNight[]>('/sleep/manual') })
}

function useInvalidateSleep() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['sleep'] })
    void client.invalidateQueries({ queryKey: ['today'] })
  }
}

export function useAddNight() {
  const invalidate = useInvalidateSleep()
  return useMutation({
    mutationFn: (data: { start_at: string; end_at: string; awake_minutes: number }) => post<SleepNight>('/sleep/manual', data),
    onSuccess: invalidate,
  })
}

export function useDeleteNight() {
  const invalidate = useInvalidateSleep()
  return useMutation({ mutationFn: (id: number) => del(`/sleep/manual/${id}`), onSuccess: invalidate })
}
