import { useQuery } from '@tanstack/react-query'

import { api } from './client'
import type { HealthSummary } from './types'

export function useHealthSummary(days = 30) {
  return useQuery({
    queryKey: ['sleep', 'summary', days],
    queryFn: () => api<HealthSummary>(`/sleep/summary?days=${days}`),
  })
}
