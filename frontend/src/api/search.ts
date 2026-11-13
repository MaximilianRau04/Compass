import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api } from './client'
import type { CalendarEvent, Mail, NoteListItem, Task } from './types'

export interface SearchResults {
  tasks: Task[]
  notes: NoteListItem[]
  events: CalendarEvent[]
  mails: Mail[]
}

export const SEARCH_MIN = 2

/** Tasks, notes, events and mails that contain the words of q. Not kept on the device (see
 * lib/queryCache): every keystroke would leave an entry behind. */
export function useSearch(q: string) {
  return useQuery({
    queryKey: ['search', q],
    queryFn: () => api<SearchResults>(`/search?${new URLSearchParams({ q })}`),
    enabled: q.length >= SEARCH_MIN,
    placeholderData: keepPreviousData,
    gcTime: 5 * 60_000,
  })
}
