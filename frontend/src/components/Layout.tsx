import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'

import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { usePreferences } from '../lib/preferences'
import { SettingsDialog } from '../pages/Settings'
import { Search, SearchIcon } from './Search'

interface NavItem {
  to: string
  label: MessageKey
  icon: string
}

// Pages can be hidden in the settings; the settings open from the profile below them.
const NAV: NavItem[] = [
  { to: '/', label: 'nav.today', icon: 'M12 3v2M12 19v2M3 12h2M19 12h2M12 8l2 4-2 4-2-4z' },
  { to: '/tasks', label: 'nav.tasks', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/calendar', label: 'nav.calendar', icon: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4' },
  { to: '/mail', label: 'nav.mail', icon: 'M4 6h16v12H4zM4 7l8 6 8-6' },
  { to: '/training', label: 'nav.training', icon: 'M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12'},
  { to: '/sleep', label: 'nav.sleep', icon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z'},
  { to: '/nutrition', label: 'nav.nutrition', icon: 'M7 3v8M5 3v4a2 2 0 0 0 4 0V3M7 11v10M17 21V3c-2 1-3 4-3 8h3'},
  { to: '/notes', label: 'nav.notes', icon: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5'},
  { to: '/journal', label: 'nav.journal', icon: 'M6 3h12v18H6zM9 3v18M12 8h4M12 12h4' },
  { to: '/correlations', label: 'nav.correlations', icon: 'M4 20h16M4 20V4M8 15h.01M11 11h.01M14 13h.01M17 7h.01' },
  { to: '/news', label: 'nav.news', icon: 'M5 4h11v16H6a1 1 0 0 1-1-1zM16 8h3v11a1 1 0 0 1-1 1h-2M8 8h5M8 12h5M8 16h3'},
  { to: '/finance', label: 'nav.finance', icon: 'M3 7h18v12H3zM3 11h18M7 15h3M16 3l-4 4-4-4'},
]
const MORE_ICON = 'M5 12h.01M12 12h.01M19 12h.01'
const PROFILE_ICON = 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0'
const DISCOVER_PAGES = ['/journal', '/correlations']
// On the phone the bottom bar has room for five entries: the first four pages, then "More".
const BAR_SIZE = 4

const isAt = (pathname: string, to: string) => (to === '/' ? pathname === '/' : pathname.startsWith(to))

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d={d} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MoreMenu({ items, onSearch, onProfile }: { items: NavItem[]; onSearch: () => void; onProfile: () => void }) {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const active = items.some((item) => isAt(pathname, item.to))
  const discover = items.filter((item) => DISCOVER_PAGES.includes(item.to))
  const other = items.filter((item) => !DISCOVER_PAGES.includes(item.to))
  const link = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      role="menuitem"
      onClick={() => setOpen(false)}
      className={({ isActive }) =>
        ['flex items-center gap-3 rounded px-3 py-2.5 text-sm', isActive ? 'bg-paper text-ink' : 'text-muted hover:text-ink'].join(' ')
      }
    >
      <Icon d={item.icon} />
      {t(item.label)}
    </NavLink>
  )
  return (
    <div className="relative flex flex-1 sm:hidden">
      {open && <button type="button" aria-hidden tabIndex={-1} className="fixed inset-0 cursor-default" onClick={() => setOpen(false)} />}
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        className={['flex flex-1 flex-col items-center gap-0.5 py-2 text-2xs', active || open ? 'text-ink' : 'text-muted'].join(' ')}
      >
        <span className={active ? 'text-brass' : ''}>
          <Icon d={MORE_ICON} />
        </span>
        {t('nav.more')}
      </button>
      {open && (
        <div role="menu" aria-label={t('nav.more')} className="absolute right-2 bottom-full mb-2 max-h-[calc(100dvh-5rem)] w-52 overflow-y-auto rounded-md border border-rule bg-paper-raised p-1 shadow-lg">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onSearch()
            }}
            className="flex w-full items-center gap-3 rounded px-3 py-2.5 text-sm text-muted hover:text-ink"
          >
            <SearchIcon />
            {t('search.title')}
          </button>
          {discover.length > 0 && (
            <div className="border-y border-rule py-1">
              <div className="px-3 py-1 font-mono text-2xs uppercase tracking-wider text-muted">{t('nav.discover')}</div>
              {discover.map(link)}
            </div>
          )}
          {other.map(link)}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onProfile()
            }}
            className="flex w-full items-center gap-3 border-t border-rule px-3 py-2.5 text-sm text-muted hover:text-ink"
          >
            <Icon d={PROFILE_ICON} />
            {t('nav.profile')}
          </button>
        </div>
      )}
    </div>
  )
}

export function Layout() {
  const { t } = useI18n()
  // The calendar grid and the today dashboard need the room; text pages stay at a readable width.
  const { pathname, state } = useLocation()
  const navigate = useNavigate()
  const wide = pathname === '/' || pathname.startsWith('/calendar')
  const { hidden } = usePreferences()
  const shown = NAV.filter((item) => !(hidden as string[]).includes(item.to))
  const bar = shown.filter((item) => !DISCOVER_PAGES.includes(item.to)).slice(0, BAR_SIZE)
  const [searching, setSearching] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // /settings (linked from push messages and the search) lands here with this state; closing clears it.
  const settingsLinked = (state as { settings?: boolean } | null)?.settings === true
  const onSettingsChange = (open: boolean) => {
    setSettingsOpen(open)
    if (!open && settingsLinked) navigate(pathname, { replace: true, state: null })
  }
  // Ctrl/Cmd+K everywhere, "/" when no field has the focus.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const typing = !!target?.closest('input, textarea, select, [contenteditable="true"]')
      const combo = (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k'
      const slash = e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey
      if (!combo && !slash) return
      e.preventDefault()
      setSearching(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return (
    <div className="min-h-dvh sm:flex">
      <nav
        aria-label={t('nav.main')}
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-rule bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:sticky sm:top-0 sm:h-dvh sm:w-52 sm:flex-col sm:border-t-0 sm:border-r sm:bg-transparent sm:px-4 sm:py-6 sm:pb-6"
      >
        <span className="mb-8 hidden px-2 text-sm font-semibold tracking-[0.2em] text-ink sm:block">
          COMPASS
        </span>
        <button
          type="button"
          onClick={() => setSearching(true)}
          aria-keyshortcuts="Control+K Meta+K /"
          className="mb-3 hidden items-center gap-3 rounded-md border border-rule px-2 py-2 text-sm text-muted hover:border-ink hover:text-ink sm:flex"
        >
          <SearchIcon />
          <span className="flex-1 text-left">{t('search.title')}</span>
          <kbd className="font-mono text-2xs">/</kbd>
        </button>
        {shown.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              [
                bar.includes(item) ? 'flex' : 'hidden sm:flex',
                'flex-1 flex-col items-center gap-0.5 py-2 text-2xs sm:flex-none sm:flex-row sm:gap-3 sm:rounded-md sm:px-2 sm:py-2 sm:text-sm',
                isActive ? 'text-ink sm:bg-paper-raised' : 'text-muted hover:text-ink',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <span className={isActive ? 'text-brass' : ''}>
                  <Icon d={item.icon} />
                </span>
                {t(item.label)}
              </>
            )}
          </NavLink>
        ))}
        <MoreMenu items={shown.filter((item) => !bar.includes(item))} onSearch={() => setSearching(true)} onProfile={() => setSettingsOpen(true)} />
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          aria-haspopup="dialog"
          className="mt-auto hidden items-center gap-3 rounded-md border-t border-rule px-2 pt-4 pb-2 text-sm text-muted hover:text-ink sm:flex"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-paper-raised text-ink">
            <Icon d={PROFILE_ICON} />
          </span>
          <span className="flex flex-col items-start leading-tight">
            <span className="text-ink">{t('nav.profile')}</span>
            <span className="text-2xs">{t('nav.settings')}</span>
          </span>
        </button>
      </nav>
      <Search open={searching} onOpenChange={setSearching} pages={[...shown, { to: '/settings', label: 'nav.settings' }]} />
      <SettingsDialog open={settingsOpen || settingsLinked} onOpenChange={onSettingsChange} />
      <main className={`mx-auto w-full ${wide ? 'max-w-6xl' : 'max-w-3xl'} px-4 pt-6 pb-44 sm:px-10 sm:pt-10 sm:pb-16`}>
        <Outlet />
      </main>
    </div>
  )
}

export function SectionLabel({ children, count, tone }: { children: string; count?: number; tone?: 'signal' }) {
  return (
    <h2
      className={[
        'flex items-baseline gap-2 border-b border-rule pb-1 text-label font-semibold tracking-[0.08em] uppercase',
        tone === 'signal' ? 'text-signal' : 'text-muted',
      ].join(' ')}
    >
      {children}
      {count !== undefined && <span className="font-mono text-2xs font-normal tracking-normal">{count}</span>}
    </h2>
  )
}
