import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, del, patch, post, put } from './client'
import type { Exercise, ImportResult, PlannedWorkout, Progression, ProgressPoint, SessionBrief, SessionDetail, TemplateExercise, TrainingSummary, WorkoutTemplate, WorkoutTemplateItem } from './types'

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

/** Upload a workout export (Gym Day, Strong or Hevy CSV) as the raw request body. */
export function useImportWorkouts() {
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
    mutationFn: ({ id, data }: { id: number; data: Partial<Pick<Exercise, 'name' | 'muscle_group' | 'bodyweight' | 'rep_min' | 'rep_max' | 'weight_step'>> }) =>
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

export function useProgression() {
  return useQuery({ queryKey: ['training', 'progression'], queryFn: () => api<Progression>('/training/progression') })
}

export function useWorkoutNames() {
  return useQuery({ queryKey: ['training', 'workouts'], queryFn: () => api<{ name: string; last_at: string }[]>('/training/log/workouts') })
}

export const fetchTemplate = (workout: string) =>
  api<{ workout_name: string; template_id: number | null; exercises: TemplateExercise[] }>(`/training/log/template?workout=${encodeURIComponent(workout)}`)

export const fetchExerciseTarget = (id: number) => api<TemplateExercise>(`/training/log/exercises/${id}`)

export function usePlannedWorkouts() {
  return useQuery({ queryKey: ['training', 'planned'], queryFn: () => api<PlannedWorkout[]>('/training/planned') })
}

export function useTemplates() {
  return useQuery({ queryKey: ['training', 'templates'], queryFn: () => api<WorkoutTemplate[]>('/training/templates') })
}

/** Create (no id) or replace a template. */
export function useSaveTemplate() {
  const invalidate = useInvalidateTraining()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: { name: string; exercises: Partial<WorkoutTemplateItem>[]; weekdays?: number[] } }) =>
      id ? put<WorkoutTemplate>(`/training/templates/${id}`, data) : post<WorkoutTemplate>('/training/templates', data),
    onSuccess: invalidate,
  })
}

export function useDeleteTemplate() {
  const invalidate = useInvalidateTraining()
  return useMutation({ mutationFn: (id: number) => del(`/training/templates/${id}`), onSuccess: invalidate })
}

export function useDeleteSession() {
  const invalidate = useInvalidateTraining()
  return useMutation({ mutationFn: (id: number) => del(`/training/sessions/${id}`), onSuccess: invalidate })
}
