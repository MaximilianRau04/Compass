import { registerSW } from 'virtual:pwa-register'

const HOUR = 60 * 60 * 1000

/**
 * Registers the service worker and keeps the app current. With autoUpdate the new worker takes
 * over as soon as it is installed and the page reloads once on its own, so nobody sees the old
 * version after a deploy. The installed app can stay open for days, so it also asks for an update
 * every hour and whenever it comes back to the foreground.
 */
export function registerServiceWorker() {
  registerSW({
    immediate: true,
    onRegisteredSW(_url, registration) {
      if (!registration) return
      const check = () => {
        if (registration.installing || !navigator.onLine) return
        registration.update().catch(() => {})
      }
      setInterval(check, HOUR)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') check()
      })
    },
  })
}
