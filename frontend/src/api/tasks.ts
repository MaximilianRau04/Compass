import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, patch, post } from './client'
import { toIsoDate } from '../lib/format'
import type { Area, QuickAddPreview, Task, TaskEvent, TaskStatus, TaskUpdate, TodayOverview } from './types'

export const keys = {
  today: ['today'] as const,
  tasks: (filters: TaskFilters) => ['tasks', filters] as const,
  areas: ['areas'] as const,
  events: (id: number) => ['task-events', id] as const,
  preview: (text: string) => ['quick-preview', text] as const,
}

export interface TaskFilters {
  status?: TaskStatus[]
  areaId?: number | null
  q?: string
}

export function useToday() {
  return useQuery({ queryKey: keys.today, queryFn: () => api<TodayOverview>('/today') })
}

/** Today's date from the server (Europe/Berlin), with the device date as fallback while loading. */
export function useTodayDate(): string {
  const [fallback] = useState(() => toIsoDate(new Date()))
  return useToday().data?.today ?? fallback
}

export function useTasks(filters: TaskFilters) {
  const params = new URLSearchParams()
  filters.status?.forEach((s) => params.append('status', s))
  if (filters.areaId) params.set('area_id', String(filters.areaId))
  if (filters.q) params.set('q', filters.q)
  return useQuery({
    queryKey: keys.tasks(filters),
    queryFn: () => api<Task[]>(`/tasks?${params}`),
    placeholderData: keepPreviousData,
  })
}

export function useAreas() {
  return useQuery({ queryKey: keys.areas, queryFn: () => api<Area[]>('/areas'), staleTime: 5 * 60_000 })
}

export function useTaskEvents(id: number | null) {
  return useQuery({
    queryKey: keys.events(id ?? 0),
    queryFn: () => api<TaskEvent[]>(`/tasks/${id}/events`),
    enabled: id !== null,
  })
}

export function useQuickAddPreview(text: string) {
  return useQuery({
    queryKey: keys.preview(text),
    queryFn: () => post<QuickAddPreview>('/tasks/quick/preview', { text }),
    enabled: text.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

function useInvalidateTasks() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: keys.today })
    void client.invalidateQueries({ queryKey: ['tasks'] })
    void client.invalidateQueries({ queryKey: ['task-events'] })
  }
}

export function useQuickAdd() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (text: string) => post<Task>('/tasks/quick', { text }),
    onSuccess: invalidate,
  })
}

export function useUpdateTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TaskUpdate }) => patch<Task>(`/tasks/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useToggleDone() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (task: Task) =>
      post<Task>(`/tasks/${task.id}/${task.status === 'done' ? 'reopen' : 'complete'}`),
    onSuccess: invalidate,
  })
}
