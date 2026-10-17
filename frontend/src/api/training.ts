import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, patch, post } from './client'
import type { Exercise, ImportResult, ProgressPoint, SessionBrief, SessionDetail, TrainingSummary } from './types'

const keys = {
  summary: (weeks: number) => ['training', 'summary', weeks] as const,
  sessions: ['training', 'sessions'] as const,
  session: (id: number) => ['training', 'session', id] as const,
  exercises: ['training', 'exercises'] as const,
  progress: (id: number) => ['training', 'progress', id] as const,
}

export function useTrainingSummary(weeks = 12) {
  return useQuery({ queryKey: keys.summary(weeks), queryFn: () => api<TrainingSummary>(`/training/summary?weeks=${weeks}`) })
}

export function useSessions() {
  return useQuery({ queryKey: keys.sessions, queryFn: () => api<SessionBrief[]>('/training/sessions?limit=15') })
}

export function useSessionDetail(id: number | null) {
  return useQuery({
    queryKey: keys.session(id ?? 0),
    queryFn: () => api<SessionDetail>(`/training/sessions/${id}`),
    enabled: id !== null,
  })
}

export function useExercises() {
  return useQuery({ queryKey: keys.exercises, queryFn: () => api<Exercise[]>('/training/exercises') })
}

export function useProgress(id: number | null) {
  return useQuery({
    queryKey: keys.progress(id ?? 0),
    queryFn: () => api<ProgressPoint[]>(`/training/exercises/${id}/progress`),
    enabled: id !== null,
  })
}

function useInvalidateTraining() {
  const client = useQueryClient()
  return () => void client.invalidateQueries({ queryKey: ['training'] })
}

/** Upload a Gym Day export (daily_strength.csv) as the raw request body. */
export function useImportGymDay() {
  const invalidate = useInvalidateTraining()
  return useMutation({
    mutationFn: (file: Blob) =>
      api<ImportResult>('/training/import', { method: 'POST', body: file, headers: { 'Content-Type': 'text/csv' } }),
    onSuccess: invalidate,
  })
}

export function useUpdateExercise() {
  const invalidate = useInvalidateTraining()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Pick<Exercise, 'name' | 'muscle_group' | 'bodyweight'>> }) =>
      patch<Exercise>(`/training/exercises/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useMergeExercise() {
  const invalidate = useInvalidateTraining()
  return useMutation({
    mutationFn: ({ id, into }: { id: number; into: number }) => post<Exercise>(`/training/exercises/${id}/merge`, { into }),
    onSuccess: invalidate,
  })
}
