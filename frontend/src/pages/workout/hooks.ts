/** State of the workout logger: the draft and its sync, the clock, the wake lock and the rest timer. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { type Draft, loadDraft, loadRest, type RestTimer, sendDraft, storeDraft, storeRest } from '../../lib/workout'

export type Sync = 'saved' | 'saving' | 'pending' | 'offline'

export const nowIso = () => new Date().toISOString()

/** Keeps the draft in localStorage and on the server; retries until the server has the last change. */
export function useDraft() {
  const [draft, setDraftState] = useState<Draft | null>(() => loadDraft())
  const [sync, setSync] = useState<Sync>('saved')
  const latest = useRef(draft)
  // Declared before the effects that send, so they always see the current draft.
  useEffect(() => {
    latest.current = draft
  }, [draft])

  const setDraft = useCallback((update: (d: Draft) => Draft) => {
    setDraftState((d) => {
      if (!d) return d
      const next = { ...update(d), changed_at: nowIso() }
      storeDraft(next)
      return next
    })
  }, [])

  const push = useCallback(async () => {
    const d = latest.current
    if (!d || (d.synced_at && d.synced_at >= d.changed_at)) return true
    const hasSets = d.exercises.some((e) => e.sets.some((s) => s.done))
    if (!hasSets && !d.synced_at) return true // nothing worth a session on the server yet
    setSync('saving')
    try {
      await sendDraft(d)
      setDraftState((current) => {
        if (!current || current.client_id !== d.client_id) return current
        const next = { ...current, synced_at: d.changed_at }
        storeDraft(next)
        return next
      })
      setSync('saved')
      return true
    } catch {
      setSync(navigator.onLine ? 'pending' : 'offline')
      return false
    }
  }, [])

  // Send a second after the last change, and keep trying while something is unsent.
  useEffect(() => {
    if (!draft || (draft.synced_at && draft.synced_at >= draft.changed_at)) return
    const id = setTimeout(() => void push(), 1000)
    return () => clearTimeout(id)
  }, [draft, push])
  useEffect(() => {
    const retry = () => void push()
    window.addEventListener('online', retry)
    const id = setInterval(retry, 20_000)
    return () => {
      window.removeEventListener('online', retry)
      clearInterval(id)
    }
  }, [push])

  const start = (d: Draft) => {
    storeDraft(d)
    setDraftState(d)
  }
  const clear = () => {
    storeDraft(null)
    storeRest(null)
    setDraftState(null)
  }
  return { draft, setDraft, sync, push, start, clear }
}

/** The current time, every second. */
export function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const id = setInterval(tick, 1000)
    // Timers sleep in the background; catch up as soon as the page is back.
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [])
  return now
}

/** Keeps the screen on during the workout, so the clock and the rest timer stay in view. */
export function useWakeLock(enabled: boolean) {
  useEffect(() => {
    if (!enabled || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let gone = false
    const acquire = async () => {
      if (document.visibilityState !== 'visible' || gone) return
      try {
        lock = await navigator.wakeLock.request('screen')
      } catch {
        // Battery saver or not allowed: the timers still work, the screen just may turn off.
      }
    }
    void acquire()
    document.addEventListener('visibilitychange', acquire)
    return () => {
      gone = true
      document.removeEventListener('visibilitychange', acquire)
      void lock?.release().catch(() => undefined)
    }
  }, [enabled])
}

let audio: AudioContext | null = null

/** Audio has to be started by a tap; marking a set done is one, so the end of the rest can beep. */
export function unlockAudio() {
  try {
    audio ??= new AudioContext()
    if (audio.state === 'suspended') void audio.resume()
  } catch {
    audio = null
  }
}

export function beep() {
  if (!audio) return
  const start = audio.currentTime
  for (const [offset, freq] of [
    [0, 880],
    [0.22, 880],
    [0.44, 1320],
  ]) {
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.0001, start + offset)
    gain.gain.exponentialRampToValueAtTime(0.25, start + offset + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.18)
    osc.connect(gain).connect(audio.destination)
    osc.start(start + offset)
    osc.stop(start + offset + 0.2)
  }
}

export function useRestTimer() {
  const [rest, setRestState] = useState<RestTimer | null>(() => loadRest())
  const setRest = useCallback((next: RestTimer | null) => {
    storeRest(next)
    setRestState(next)
  }, [])
  return { rest, setRest }
}
