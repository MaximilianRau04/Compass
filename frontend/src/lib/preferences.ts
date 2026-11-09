import { useSyncExternalStore } from 'react'

import type { MessageKey } from '../i18n/messages'

/*
 * Personal settings of this device: design, accent, text size, motion, units, the page the app
 * opens on and the hidden navigation entries. They live in localStorage like the language, so
 * each device keeps its own. public/prefs.js applies the look before the first paint; this module
 * keeps it current afterwards.
 */

export type Theme = 'system' | 'light' | 'dark'
export type Accent = 'brass' | 'sea' | 'blue' | 'violet'
export type TextSize = 'normal' | 'large' | 'larger'
export type Motion = 'system' | 'on' | 'off'
export type Units = 'metric' | 'imperial'

export const THEMES: Theme[] = ['system', 'light', 'dark']
export const ACCENTS: Accent[] = ['brass', 'sea', 'blue', 'violet']
export const TEXT_SIZES: TextSize[] = ['normal', 'large', 'larger']
export const MOTIONS: Motion[] = ['system', 'on', 'off']
export const UNITS: Units[] = ['metric', 'imperial']

/** The pages in the navigation, with their name there. Each can be the start page or be hidden. */
export const PAGES = {
  '/': 'nav.today',
  '/tasks': 'nav.tasks',
  '/calendar': 'nav.calendar',
  '/mail': 'nav.mail',
  '/training': 'nav.training',
  '/sleep': 'nav.sleep',
  '/nutrition': 'nav.nutrition',
  '/notes': 'nav.notes',
  '/news': 'nav.news',
  '/finance': 'nav.finance',
} satisfies Record<string, MessageKey>
export type Page = keyof typeof PAGES
const PAGE_PATHS = Object.keys(PAGES) as Page[]

export interface Preferences {
  theme: Theme
  accent: Accent
  textSize: TextSize
  motion: Motion
  units: Units
  start: Page
  hidden: Page[]
}

const DEFAULTS: Preferences = { theme: 'system', accent: 'brass', textSize: 'normal', motion: 'system', units: 'metric', start: '/', hidden: [] }

const KEYS: Record<keyof Preferences, string> = {
  theme: 'compass.theme',
  accent: 'compass.accent',
  textSize: 'compass.textSize',
  motion: 'compass.motion',
  units: 'compass.units',
  start: 'compass.start',
  hidden: 'compass.hiddenNav',
}

const ONE_OF: { [K in Exclude<keyof Preferences, 'hidden'>]: readonly Preferences[K][] } = {
  theme: THEMES,
  accent: ACCENTS,
  textSize: TEXT_SIZES,
  motion: MOTIONS,
  units: UNITS,
  start: PAGE_PATHS,
}

// The page color of each design, for the browser bar (meta theme-color); the same as --paper.
const PAPER = { light: '#EEF2F0', dark: '#0F1A24' }

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')
const reduceQuery = () => window.matchMedia('(prefers-reduced-motion: reduce)')

function load(): Preferences {
  const stored = (key: keyof Preferences) => {
    try {
      return localStorage.getItem(KEYS[key])
    } catch {
      // Storage can be unavailable (private mode); the default applies.
      return null
    }
  }
  const one = <K extends keyof typeof ONE_OF>(key: K): Preferences[K] => {
    const value = stored(key)
    return value !== null && (ONE_OF[key] as readonly string[]).includes(value) ? (value as Preferences[K]) : DEFAULTS[key]
  }
  // A comma list of paths; unknown ones (a page that was removed) are dropped.
  const hidden = (stored('hidden') ?? '').split(',').filter((p): p is Page => (PAGE_PATHS as string[]).includes(p))
  return { theme: one('theme'), accent: one('accent'), textSize: one('textSize'), motion: one('motion'), units: one('units'), start: one('start'), hidden }
}

let current = load()
const listeners = new Set<() => void>()

function apply() {
  const root = document.documentElement
  const dark = current.theme === 'dark' || (current.theme === 'system' && darkQuery().matches)
  const reduce = current.motion === 'off' || (current.motion === 'system' && reduceQuery().matches)
  root.dataset.theme = dark ? 'dark' : 'light'
  root.dataset.motion = reduce ? 'reduce' : 'full'
  root.dataset.accent = current.accent
  root.dataset.textSize = current.textSize
  // index.html has one theme-color per system scheme; a fixed choice sets both to its color.
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const scheme = meta.media.includes('dark') ? 'dark' : 'light'
    meta.content = current.theme === 'system' ? PAPER[scheme] : PAPER[dark ? 'dark' : 'light']
  }
}

function changed() {
  apply()
  for (const listener of listeners) listener()
}

export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]) {
  current = { ...current, [key]: value }
  const text = Array.isArray(value) ? value.join(',') : (value as string)
  const fallback = Array.isArray(DEFAULTS[key]) ? (DEFAULTS[key] as string[]).join(',') : DEFAULTS[key]
  try {
    if (text === fallback) localStorage.removeItem(KEYS[key])
    else localStorage.setItem(KEYS[key], text)
  } catch {
    // Not persisted; the choice still applies for this session.
  }
  changed()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function usePreferences(): Preferences {
  return useSyncExternalStore(subscribe, () => current)
}

/** The current choice outside of React, e.g. when a workout starts. */
export const preferences = () => current

/** Takes over from public/prefs.js: follows changes of the system setting and of other tabs. */
export function initPreferences() {
  apply()
  darkQuery().addEventListener('change', apply)
  reduceQuery().addEventListener('change', apply)
  window.addEventListener('storage', (event) => {
    if (event.key === null || Object.values(KEYS).includes(event.key)) {
      current = load()
      changed()
    }
  })
}

/** Whether animations are off, by the user's choice or the system setting. */
export const reducedMotion = () => document.documentElement.dataset.motion === 'reduce'

/**
 * Opens the chosen start page when the app is opened on / (the installed app always starts
 * there). A reload, going back or a link with parameters (the "New task" shortcut) stays put.
 */
export function openStartPage() {
  if (current.start === '/' || location.pathname !== '/' || location.search || location.hash) return
  const [entry] = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[]
  if (entry && entry.type !== 'navigate') return
  history.replaceState(null, '', current.start)
}
