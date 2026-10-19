import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, patch, post } from './client'
import type { Note, NoteDraft, NoteListItem } from './types'

export interface NoteFilters {
  q?: string
  areaId?: number
  tag?: string
  archived?: boolean
  taskId?: number
}

export function useNotes(filters: NoteFilters, enabled = true) {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.areaId) params.set('area_id', String(filters.areaId))
  if (filters.tag) params.set('tag', filters.tag)
  if (filters.archived) params.set('archived', 'true')
  if (filters.taskId) params.set('task_id', String(filters.taskId))
  return useQuery({
    queryKey: ['notes', 'list', filters],
    queryFn: () => api<NoteListItem[]>(`/notes?${params}`),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useNote(id: number | null) {
  return useQuery({ queryKey: ['notes', 'one', id], queryFn: () => api<Note>(`/notes/${id}`), enabled: id !== null })
}

export function useNoteTags() {
  return useQuery({ queryKey: ['notes', 'tags'], queryFn: () => api<{ tag: string; count: number }[]>('/notes/tags') })
}

function useInvalidateNotes() {
  const client = useQueryClient()
  return () => void client.invalidateQueries({ queryKey: ['notes'] })
}

export function useCreateNote() {
  const invalidate = useInvalidateNotes()
  return useMutation({ mutationFn: (data: NoteDraft & { title: string }) => post<Note>('/notes', data), onSuccess: invalidate })
}

export function useQuickNote() {
  const invalidate = useInvalidateNotes()
  return useMutation({ mutationFn: (text: string) => post<Note>('/notes/quick', { text }), onSuccess: invalidate })
}

export function useUpdateNote() {
  const invalidate = useInvalidateNotes()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: NoteDraft }) => patch<Note>(`/notes/${id}`, data),
    onSuccess: invalidate,
  })
}
