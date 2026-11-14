import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, del, post, put } from './client'

export type HabitRule = 'steps_goal' | 'protein_goal' | 'sleep_need' | 'journal'

export interface Habit {
  id: number
  name: string
  /** null: ticked by hand */
  rule: HabitRule | null
  done_today: boolean
  /** Days in a row up to today */
  streak: number
  /** The last 60 days, oldest first, today last */
  days: boolean[]
}

export function useHabits() {
  return useQuery({ queryKey: ['habits'], queryFn: () => api<Habit[]>('/habits') })
}

function useInvalidate() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: ['habits'] })
}

export function useCreateHabit() {
  const onSuccess = useInvalidate()
  return useMutation({ mutationFn: (data: { name: string; rule: HabitRule | null }) => post<{ id: number }>('/habits', data), onSuccess })
}

export function useCheckHabit() {
  const onSuccess = useInvalidate()
  return useMutation({
    mutationFn: ({ id, day, done }: { id: number; day: string; done: boolean }) => put<null>(`/habits/${id}/check`, { day, done }),
    onSuccess,
  })
}

export function useArchiveHabit() {
  const onSuccess = useInvalidate()
  return useMutation({ mutationFn: (id: number) => del(`/habits/${id}`), onSuccess })
}
