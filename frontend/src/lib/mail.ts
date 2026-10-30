import type { Mail } from '../api/types'

/** An account name from the server's configuration, e.g. "gmail", for display. */
export const accountName = (name: string) => name.charAt(0).toUpperCase() + name.slice(1)

/** Same rule as the server: high priority or something to do. */
export const isImportant = (m: Mail) => m.priority === 'high' || m.needs_action === true
