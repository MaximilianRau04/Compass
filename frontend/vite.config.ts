import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  // Changes with every build; the stored API answers of an older build are dropped (lib/queryCache).
  define: { __APP_BUILD__: JSON.stringify(Date.now().toString(36)) },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // Registered in src/lib/pwa.ts, which also reloads the page once a new version took over.
      injectRegister: false,
      // The app sits behind basic auth; without credentials Chrome cannot load the manifest.
      useCredentials: true,
      includeAssets: ['favicon.ico', 'apple-touch-icon-180x180.png', 'icon.svg'],
      manifest: {
        name: 'Compass',
        short_name: 'Compass',
        description: 'Aufgaben, Termine und deinen Tag im Blick',
        lang: 'de',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#F5F3EE',
        theme_color: '#252823',
        icons: [
          { src: 'pwa-64x64.png', sizes: '64x64', type: 'image/png' },
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
        // POST so files can be shared too (Gym Day export); share-target-sw.js handles it.
        share_target: {
          action: '/share',
          method: 'POST',
          enctype: 'multipart/form-data',
          params: {
            title: 'title',
            text: 'text',
            url: 'url',
            files: [
              {
                name: 'file',
                accept: ['text/csv', 'text/comma-separated-values', 'text/plain', 'application/csv', '.csv', 'application/zip', '.zip'],
              },
            ],
          },
        },
        shortcuts: [{ name: 'New task', url: '/?new=1' }],
      },
      workbox: {
        // Offline only the app shell; data always comes from the API.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        importScripts: ['share-target-sw.js', 'push-sw.js'],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
