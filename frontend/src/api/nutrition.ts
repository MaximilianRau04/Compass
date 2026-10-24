import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, post } from './client'
import type { BodyTrend, GoalMetric, MfpImportResult, NutritionSummary, WeightPoint } from './types'

export function useNutritionSummary(days = 30) {
  return useQuery({
    queryKey: ['nutrition', 'summary', days],
    queryFn: () => api<NutritionSummary>(`/nutrition/summary?days=${days}`),
  })
}

export function useWeights() {
  return useQuery({ queryKey: ['nutrition', 'weight'], queryFn: () => api<WeightPoint[]>('/nutrition/weight') })
}

export function useSetGoal() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ metric, value }: { metric: GoalMetric; value: number }) =>
      api(`/nutrition/goals/${metric}`, { method: 'PUT', body: JSON.stringify({ value }) }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['nutrition'] }),
  })
}

/** Upload a MyFitnessPal export (the zip or one of its CSV files) as the raw request body. */
export function useImportMfp() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (file: Blob) =>
      api<MfpImportResult>('/nutrition/import', {
        method: 'POST',
        body: file,
        headers: { 'Content-Type': 'application/octet-stream' },
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['nutrition'] }),
  })
}

export function useBodyTrend(weeks = 8) {
  return useQuery({ queryKey: ['nutrition', 'body', weeks], queryFn: () => api<BodyTrend>(`/body/trend?weeks=${weeks}`) })
}

export function useLogBody() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (data: { metric: 'weight' | 'waist'; value: number }) => post<BodyTrend>('/body/log', data),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['nutrition'] }),
  })
}
