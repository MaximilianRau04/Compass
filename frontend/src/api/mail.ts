import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, del, post } from './client'
import type { Mail, MailOverview, SignInPoll, SignInStart, Task } from './types'

export function useMails(params: { days: number; account?: string; dismissed?: boolean }) {
  const query = new URLSearchParams({ days: String(params.days) })
  if (params.account) query.set('account', params.account)
  if (params.dismissed) query.set('dismissed', 'true')
  return useQuery({ queryKey: ['mail', 'list', params], queryFn: () => api<Mail[]>(`/mail?${query}`) })
}

/** One mail by its id, for a link from the search: the list only reaches back some days. */
export function useMail(id: number | null) {
  return useQuery({ queryKey: ['mail', 'one', id], queryFn: () => api<Mail>(`/mail/${id}`), enabled: id !== null, retry: false })
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

/** Microsoft sign-in of a mail account: start gives the code to enter, poll asks once whether
 * the user finished. The tokens stay on the server. */
export function useStartSignIn() {
  return useMutation({ mutationFn: (account: string) => post<SignInStart>(`/mail/accounts/${encodeURIComponent(account)}/signin`) })
}

export const pollSignIn = (account: string) => post<SignInPoll>(`/mail/accounts/${encodeURIComponent(account)}/signin/poll`)

export function useSignOut() {
  const invalidate = useInvalidateMail()
  return useMutation({ mutationFn: (account: string) => del(`/mail/accounts/${encodeURIComponent(account)}/signin`), onSuccess: invalidate })
}
