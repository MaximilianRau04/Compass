import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, post } from './client'
import { keys as taskKeys } from './tasks'
import type { CalendarEvent, IntegrationState } from './types'

export const calendarKeys = {
  range: (start: string, end: string) => ['calendar', start, end] as const,
  integrations: ['integrations'] as const,
}

/** Events overlapping the days start..end (both inclusive, YYYY-MM-DD). */
export function useCalendar(start: string, end: string) {
  return useQuery({
    queryKey: calendarKeys.range(start, end),
    queryFn: () => api<CalendarEvent[]>(`/calendar?start=${start}&end=${end}`),
    staleTime: 5 * 60_000,
  })
}

export function useIntegrations() {
  return useQuery({ queryKey: calendarKeys.integrations, queryFn: () => api<IntegrationState[]>('/integrations') })
}

export function useSyncCalendars() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => post<Record<string, Record<string, unknown> | string>>('/calendar/sync'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['calendar'] })
      void client.invalidateQueries({ queryKey: calendarKeys.integrations })
      void client.invalidateQueries({ queryKey: taskKeys.today })
      void client.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}
