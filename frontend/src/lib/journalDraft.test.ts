import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { JournalEntry } from '../api/journal'
import { clearJournalDraft, loadJournalDraft, saveJournalDraft } from './journalDraft'

const values = { mood: 4, energy: 2, text: 'A good day' }
const entry: JournalEntry = { local_date: '2026-11-18', ...values, updated_at: '2026-11-18T12:00:00Z' }
const items = new Map<string, string>()

beforeEach(() => {
  items.clear()
  vi.stubGlobal('window', { localStorage: {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => { items.set(key, value) },
    removeItem: (key: string) => { items.delete(key) },
  } })
})

describe('journal drafts', () => {
  it('keeps drafts separate by day and clears them after saving', () => {
    saveJournalDraft('2026-11-18', { ...values, text: 'Unsaved' }, entry.updated_at)
    expect(loadJournalDraft('2026-11-18', entry).text).toBe('Unsaved')
    expect(loadJournalDraft('2026-11-17', null).text).toBe('')
    clearJournalDraft('2026-11-18')
    expect(loadJournalDraft('2026-11-18', entry)).toEqual(values)
  })

  it('does not restore an old draft over a newer saved entry', () => {
    saveJournalDraft('2026-11-18', { ...values, text: 'Old draft' }, entry.updated_at)
    expect(loadJournalDraft('2026-11-18', { ...entry, updated_at: '2026-11-18T13:00:00Z' })).toEqual(values)
    expect(items.size).toBe(0)
  })

  it('ignores invalid or unavailable storage', () => {
    items.set('compass.journalDraft.2026-11-18', '{bad json')
    expect(loadJournalDraft('2026-11-18', entry)).toEqual(values)
    vi.stubGlobal('window', { get localStorage() { throw new Error('blocked') } })
    expect(loadJournalDraft('2026-11-18', entry)).toEqual(values)
    expect(saveJournalDraft('2026-11-18', values, entry.updated_at)).toBe(false)
  })
})
