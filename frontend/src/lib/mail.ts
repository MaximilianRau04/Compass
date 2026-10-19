import type { Mail } from '../api/types'

/** Same rule as the server: high priority or something to do. */
export const isImportant = (m: Mail) => m.priority === 'high' || m.needs_action === true
