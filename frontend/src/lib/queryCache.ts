import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { defaultShouldDehydrateQuery, QueryClient } from '@tanstack/react-query'
import type { PersistQueryClientOptions } from '@tanstack/react-query-persist-client'

const DAY = 24 * 60 * 60 * 1000

/* The answers of the API are kept in localStorage, so the app shows the last known data at once
 * when it opens and refreshes it in the background, instead of waiting on a cold server. They
 * stay on this device only and are dropped after a day or with every new build (the shape of an
 * answer may have changed). */

export const queryClient = new QueryClient({
  defaultOptions: {
    // gcTime at least maxAge, or restored answers would be thrown away right after the restore.
    queries: { staleTime: 15_000, gcTime: DAY, refetchOnWindowFocus: true, retry: 1 },
  },
})

function storage(): Storage | undefined {
  // Private windows or blocked site data throw on access; then nothing is kept.
  try {
    const store = window.localStorage
    store.getItem('compass-cache')
    return store
  } catch {
    return undefined
  }
}

export const persistOptions: Omit<PersistQueryClientOptions, 'queryClient'> = {
  persister: createSyncStoragePersister({ storage: storage(), key: 'compass-cache', throttleTime: 2000 }),
  maxAge: DAY,
  buster: __APP_BUILD__,
  // Search answers are not kept: every query typed would stay in the storage for a day.
  dehydrateOptions: { shouldDehydrateQuery: (query) => defaultShouldDehydrateQuery(query) && query.queryKey[0] !== 'search' },
}
