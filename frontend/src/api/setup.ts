import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, post } from './client'

export type SetupSource = 'calendars' | 'health' | 'mail' | 'news' | 'finance' | 'push'

export interface Setup {
  first_run: boolean
  timezone: string
  language: string
  sources: Record<SetupSource, boolean>
}

export function useSetup() {
  return useQuery({ queryKey: ['setup'], queryFn: () => api<Setup>('/setup'), staleTime: 5 * 60_000 })
}

export function useFinishSetup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post('/setup/done', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['setup'] }),
  })
}
