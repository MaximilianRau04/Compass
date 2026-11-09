/*
 * Applies the look chosen in the settings (design, accent, text size, motion) before the first
 * paint, so a dark page never flashes light and the text does not jump. A plain script from the
 * same origin because the CSP allows no inline scripts. The same rules live in
 * src/lib/preferences.ts, which takes over once the app runs.
 */
;(function () {
  var get = function (key, fallback) {
    try {
      return localStorage.getItem('compass.' + key) || fallback
    } catch {
      // Storage can be unavailable (private mode); the default applies.
      return fallback
    }
  }
  var theme = get('theme', 'system')
  var motion = get('motion', 'system')
  var root = document.documentElement
  var dark = theme === 'dark' || (theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches)
  var reduce = motion === 'off' || (motion !== 'on' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  root.dataset.theme = dark ? 'dark' : 'light'
  root.dataset.motion = reduce ? 'reduce' : 'full'
  root.dataset.accent = get('accent', 'brass')
  root.dataset.textSize = get('textSize', 'normal')
})()
