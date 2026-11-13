import type { Task } from '../api/types'
import type { Translate } from '../i18n/context'

/** A translation that shows its key and values, so tests do not depend on the wording. */
export const t: Translate = (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key)

export function task(fields: Partial<Task> = {}): Task {
  return {
    id: 1,
    title: 'Task',
    notes: null,
    area_id: null,
    area: null,
    tags: [],
    priority: 'normal',
    status: 'open',
    due_date: null,
    due_time: null,
    scheduled_date: null,
    completed_at: null,
    recurrence: null,
    source: 'manual',
    external_id: null,
    sort_order: 0,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    ...fields,
  }
}
