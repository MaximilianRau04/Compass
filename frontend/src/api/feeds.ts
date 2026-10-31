import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { calendarKeys } from './calendar'
import { api, post } from './client'

export type FeedKind = 'calendar' | 'news'
export type NewsStream = 'general' | 'personal'

export interface Feed {
  name: string
  host: string | null
  origin: 'env' | 'app'
  hidden: boolean
  stream: NewsStream | null
  area: string | null
  deadline_pattern: string | null
}

export interface Feeds {
  calendars: Feed[]
  news: Feed[]
  config_error: string | null
}

export interface NewCalendarFeed {
  name: string
  url: string
  area: string | null
  deadline_pattern: string | null
}

export interface NewNewsFeed {
  name: string
  url: string
  stream: NewsStream
}

export function useFeeds() {
  return useQuery({ queryKey: ['feeds'], queryFn: () => api<Feeds>('/feeds') })
}

function useInvalidate() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['feeds'] })
    void client.invalidateQueries({ queryKey: ['setup'] })
    void client.invalidateQueries({ queryKey: ['news'] })
    void client.invalidateQueries({ queryKey: ['calendar'] })
    void client.invalidateQueries({ queryKey: calendarKeys.integrations })
    void client.invalidateQueries({ queryKey: ['tasks'] })
  }
}

export function useAddCalendarFeed() {
  const onSuccess = useInvalidate()
  return useMutation({ mutationFn: (feed: NewCalendarFeed) => post<Feed>('/feeds/calendar', feed), onSuccess })
}

export function useAddNewsFeed() {
  const onSuccess = useInvalidate()
  return useMutation({ mutationFn: (feed: NewNewsFeed) => post<Feed>('/feeds/news', feed), onSuccess })
}

export function useRemoveFeed() {
  const onSuccess = useInvalidate()
  return useMutation({
    mutationFn: ({ kind, name }: { kind: FeedKind; name: string }) => api(`/feeds/${kind}/${name}`, { method: 'DELETE' }),
    onSuccess,
  })
}

export function useRestoreFeed() {
  const onSuccess = useInvalidate()
  return useMutation({
    mutationFn: ({ kind, name }: { kind: FeedKind; name: string }) => post(`/feeds/${kind}/${name}/restore`),
    onSuccess,
  })
}
