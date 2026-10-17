/* Web Share Target: Android posts shared text and files to /share. A static server cannot take
 * that POST, so the service worker answers it: it keeps a shared file in a cache for the share
 * page to pick up and redirects to /share with the text fields as query parameters.
 * Loaded into the generated service worker via workbox.importScripts (see vite.config.ts). */

const SHARE_CACHE = 'compass-share'
const SHARED_FILE = '/__shared/file'

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'POST' || url.pathname !== '/share') return

  event.respondWith(
    (async () => {
      const form = await event.request.formData()
      const params = new URLSearchParams()
      for (const key of ['title', 'text', 'url']) {
        const value = form.get(key)
        if (typeof value === 'string' && value.trim()) params.set(key, value)
      }
      const file = form.get('file')
      if (file && typeof file !== 'string' && file.size > 0) {
        const cache = await caches.open(SHARE_CACHE)
        const name = file.name || 'export.csv'
        await cache.put(
          SHARED_FILE,
          new Response(file, {
            headers: { 'Content-Type': file.type || 'text/csv', 'X-File-Name': encodeURIComponent(name) },
          }),
        )
        params.set('file', name)
      }
      return Response.redirect(`/share?${params}`, 303)
    })(),
  )
})
