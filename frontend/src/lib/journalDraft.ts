import type { JournalEntry } from '../api/journal'

const key = (day: string) => `compass.journalDraft.${day}`

type Draft = { mood: number | null; energy: number | null; text: string; updated_at: string | null }

function storage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function clearJournalDraft(day: string) {
  try { storage()?.removeItem(key(day)) } catch { /* Storage may be full or disabled. */ }
}

export function saveJournalDraft(day: string, values: Pick<Draft, 'mood' | 'energy' | 'text'>, updated_at: string | null): boolean {
  try {
    const store = storage()
    if (!store) return false
    store.setItem(key(day), JSON.stringify({ ...values, updated_at }))
    return true
  } catch { return false }
}

export function loadJournalDraft(day: string, entry: JournalEntry | null): Pick<Draft, 'mood' | 'energy' | 'text'> {
  const current = { mood: entry?.mood ?? null, energy: entry?.energy ?? null, text: entry?.text ?? '' }
  try {
    const raw = storage()?.getItem(key(day))
    if (!raw) return current
    const draft: unknown = JSON.parse(raw)
    if (typeof draft !== 'object' || draft === null || !('updated_at' in draft) || draft.updated_at !== (entry?.updated_at ?? null)
      || !('mood' in draft) || !('energy' in draft) || !('text' in draft)
      || (draft.mood !== null && (!Number.isInteger(draft.mood) || (draft.mood as number) < 1 || (draft.mood as number) > 5))
      || (draft.energy !== null && (!Number.isInteger(draft.energy) || (draft.energy as number) < 1 || (draft.energy as number) > 5))
      || typeof draft.text !== 'string' || draft.text.length > 20000) {
      clearJournalDraft(day)
      return current
    }
    return { mood: draft.mood as number | null, energy: draft.energy as number | null, text: draft.text }
  } catch {
    return current
  }
}
