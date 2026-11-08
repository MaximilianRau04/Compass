import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, post } from './client'
import type { Brief, Interest, Interests, NewsItem, NewsOverview } from './types'

export function useNews(params: { hours: number; stream: 'general' | 'personal' }) {
  const query = new URLSearchParams({ hours: String(params.hours), stream: params.stream })
  return useQuery({ queryKey: ['news', 'list', params], queryFn: () => api<NewsItem[]>(`/news?${query}`) })
}

export function useNewsOverview() {
  return useQuery({ queryKey: ['news', 'overview'], queryFn: () => api<NewsOverview>('/news/overview') })
}

export function useInterests() {
  return useQuery({ queryKey: ['news', 'interests'], queryFn: () => api<Interests>('/news/interests') })
}

export function useTodayBrief() {
  return useQuery({ queryKey: ['briefs', 'today'], queryFn: () => api<Brief | null>('/briefs/today') })
}

export function useBriefs(kind?: string, limit?: number) {
  const params = new URLSearchParams()
  if (kind) params.set('kind', kind)
  if (limit) params.set('limit', String(limit))
  const query = params.toString() ? `?${params}` : ''
  return useQuery({ queryKey: ['briefs', 'list', kind, limit], queryFn: () => api<Brief[]>(`/briefs${query}`) })
}

function useInvalidateNews() {
  const client = useQueryClient()
  return () => void client.invalidateQueries({ queryKey: ['news'] })
}

export function useNewsFeedback() {
  const invalidate = useInvalidateNews()
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: 1 | -1 | null }) => post<NewsItem>(`/news/${id}/feedback`, { value }),
    onSuccess: invalidate,
  })
}

export function useSaveInterests() {
  const invalidate = useInvalidateNews()
  return useMutation({
    mutationFn: (topics: Interest[]) => api<Interests>('/news/interests', { method: 'PUT', body: JSON.stringify({ topics }) }),
    onSuccess: invalidate,
  })
}

export function useResetLearned() {
  const invalidate = useInvalidateNews()
  return useMutation({ mutationFn: () => api('/news/interests/learned', { method: 'DELETE' }), onSuccess: invalidate })
}

export function useSyncNews() {
  const invalidate = useInvalidateNews()
  return useMutation({ mutationFn: () => post<Record<string, unknown>>('/news/sync'), onSuccess: invalidate })
}
