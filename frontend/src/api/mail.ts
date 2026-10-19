import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, post } from './client'
import type { Mail, MailOverview, Task } from './types'

export function useMails(params: { days: number; account?: string; dismissed?: boolean }) {
  const query = new URLSearchParams({ days: String(params.days) })
  if (params.account) query.set('account', params.account)
  if (params.dismissed) query.set('dismissed', 'true')
  return useQuery({ queryKey: ['mail', 'list', params], queryFn: () => api<Mail[]>(`/mail?${query}`) })
}

export function useMailOverview() {
  return useQuery({ queryKey: ['mail', 'overview'], queryFn: () => api<MailOverview>('/mail/overview') })
}

function useInvalidateMail() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['mail'] })
    void client.invalidateQueries({ queryKey: ['tasks'] })
    void client.invalidateQueries({ queryKey: ['today'] })
  }
}

export function useMailToTask() {
  const invalidate = useInvalidateMail()
  return useMutation({ mutationFn: (id: number) => post<Task>(`/mail/${id}/task`), onSuccess: invalidate })
}

export function useDismissMail() {
  const invalidate = useInvalidateMail()
  return useMutation({
    mutationFn: ({ id, dismissed }: { id: number; dismissed: boolean }) => post<Mail>(`/mail/${id}/dismiss`, { dismissed }),
    onSuccess: invalidate,
  })
}

export function useSyncMail() {
  const invalidate = useInvalidateMail()
  return useMutation({ mutationFn: () => post<Record<string, unknown>>('/mail/sync'), onSuccess: invalidate })
}
