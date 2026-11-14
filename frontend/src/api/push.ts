import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { currentSubscription, pushState, subscribePush, unsubscribePush } from '../lib/push'
import { api, post } from './client'

export type PushTopic =
  | 'bedtime'
  | 'deadlines'
  | 'resting'
  | 'weekly'
  | 'finance'
  | 'sync'
  | 'claude'

export interface PushConfig {
  enabled: boolean
  public_key: string | null
  topics: PushTopic[]
  quiet_start: number
  quiet_end: number
}

export interface PushDevice {
  endpoint: string
  topics: PushTopic[]
  created_at: string
  last_sent_at: string | null
}

export function usePushConfig() {
  return useQuery({ queryKey: ['push', 'config'], queryFn: () => api<PushConfig>('/push/config'), staleTime: Infinity })
}

/** This browser: its permission/subscription state and, when subscribed, the stored topics. */
export function usePushDevice() {
  return useQuery({
    queryKey: ['push', 'device'],
    queryFn: async () => {
      const state = await pushState()
      const sub = state === 'on' ? await currentSubscription() : null
      if (!sub) return { state, device: null }
      // Subscribed in the browser but unknown to the server (e.g. removed after errors): register again.
      const device = await post<PushDevice>('/push/subscriptions/lookup', { endpoint: sub.endpoint }).catch(() =>
        post<PushDevice>('/push/subscriptions', sub.toJSON()),
      )
      return { state, device }
    },
  })
}

export function useEnablePush() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (publicKey: string) => {
      const sub = await subscribePush(publicKey)
      if (!sub) return null
      return post<PushDevice>('/push/subscriptions', sub)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['push', 'device'] }),
  })
}

export function useDisablePush() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const endpoint = await unsubscribePush()
      if (endpoint) await post('/push/subscriptions/remove', { endpoint })
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['push', 'device'] }),
  })
}

export function useSetPushTopics() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { endpoint: string; topics: PushTopic[] }) => post<PushDevice>('/push/subscriptions/topics', data),
    onSettled: () => qc.invalidateQueries({ queryKey: ['push', 'device'] }),
  })
}

export const sendTestPush = (endpoint: string) => post<{ sent: boolean }>('/push/test', { endpoint })
