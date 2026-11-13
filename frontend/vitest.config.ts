import { defineConfig } from 'vitest/config'

// The tests cover plain logic in src/lib, so they need neither the plugins of the app nor a DOM.
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
    // Local days are computed in the time zone of the device; the tests pin one with a DST change.
    env: { TZ: 'Europe/Berlin' },
  },
})
