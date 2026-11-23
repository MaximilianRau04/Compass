import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, put } from './client'

export interface JournalEntry {
  local_date: string
  /** 1 to 5 */
  mood: number | null
  /** 1 to 5 */
  energy: number | null
  text: string
  updated_at: string | null
}

export interface JournalDay {
  date: string
  entry: JournalEntry | null
  briefs: { kind: string; title: string | null; body: string }[]
  tasks_done: string[]
  notes: { id: number; title: string }[]
  training: string[]
  asleep_minutes: number | null
  steps: number | null
  resting_hr: number | null
  kcal: number | null
  protein_g: number | null
  weight_kg: number | null
}

export interface JournalWrite {
  mood?: number | null
  energy?: number | null
  text?: string | null
}

export function useJournalDay(day: string, enabled = true) {
  return useQuery({ queryKey: ['journal', 'day', day], queryFn: () => api<JournalDay>(`/journal/${day}`), enabled })
}

export function useJournal(days = 30) {
  return useQuery({ queryKey: ['journal', 'list', days], queryFn: () => api<JournalEntry[]>(`/journal?days=${days}`) })
}

export function useSaveJournal() {
  const client = useQueryClient()
  return useMutation({
    // null: the day has no entry (nothing left in it).
    mutationFn: ({ day, data }: { day: string; data: JournalWrite }) => put<JournalEntry | null>(`/journal/${day}`, data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['journal'] })
      void client.invalidateQueries({ queryKey: ['habits'] })
      void client.invalidateQueries({ queryKey: ['correlations'] })
      void client.invalidateQueries({ queryKey: ['today'] })
    },
  })
}
