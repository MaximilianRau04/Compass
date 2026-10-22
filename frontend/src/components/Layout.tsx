import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'

import { type Lang, useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'

// On the phone the bottom bar has room for five entries; `more` ones sit behind "More" there.
const NAV: { to: string; label: MessageKey; icon: string; more?: boolean }[] = [
  { to: '/', label: 'nav.today', icon: 'M12 3v2M12 19v2M3 12h2M19 12h2M12 8l2 4-2 4-2-4z' },
  { to: '/aufgaben', label: 'nav.tasks', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/kalender', label: 'nav.calendar', icon: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4' },
  { to: '/mail', label: 'nav.mail', icon: 'M4 6h16v12H4zM4 7l8 6 8-6' },
  { to: '/training', label: 'nav.training', icon: 'M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12', more: true },
  { to: '/schlaf', label: 'nav.sleep', icon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z', more: true },
  { to: '/notizen', label: 'nav.notes', icon: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5', more: true },
  { to: '/news', label: 'nav.news', icon: 'M5 4h11v16H6a1 1 0 0 1-1-1zM16 8h3v11a1 1 0 0 1-1 1h-2M8 8h5M8 12h5M8 16h3', more: true },
  { to: '/ernaehrung', label: 'nav.nutrition', icon: 'M7 3v8M5 3v4a2 2 0 0 0 4 0V3M7 11v10M17 21V3c-2 1-3 4-3 8h3', more: true },
]
const MORE_ICON = 'M5 12h.01M12 12h.01M19 12h.01'

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d={d} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function LanguageSwitch() {
  const { lang, setLang, t } = useI18n()
  return (
    <div
      role="group"
      aria-label={t('lang.label')}
      className="absolute top-3 right-3 z-30 flex rounded-full border border-rule bg-paper-raised p-0.5 font-mono text-sm sm:top-5 sm:right-6"
    >
      {(['de', 'en'] as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={code === lang}
          className={[
            'rounded-full px-3 py-1 transition-colors',
            code === lang ? 'bg-ink font-medium text-paper' : 'text-muted hover:text-ink',
          ].join(' ')}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

function MoreMenu() {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const items = NAV.filter((item) => item.more)
  const active = items.some((item) => pathname.startsWith(item.to))
  return (
    <div className="relative flex flex-1 sm:hidden">
      {open && <button type="button" aria-hidden tabIndex={-1} className="fixed inset-0 cursor-default" onClick={() => setOpen(false)} />}
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        className={['flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]', active || open ? 'text-ink' : 'text-muted'].join(' ')}
      >
        <span className={active ? 'text-brass' : ''}>
          <Icon d={MORE_ICON} />
        </span>
        {t('nav.more')}
      </button>
      {open && (
        <div role="menu" className="absolute right-2 bottom-full mb-2 w-48 rounded-md border border-rule bg-paper-raised p-1 shadow-lg">
          {items.map((item) => (
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
          ))}
        </div>
      )}
    </div>
  )
}

export function Layout() {
  const { t } = useI18n()
  // The calendar grid and the today dashboard need the room; text pages stay at a readable width.
  const { pathname } = useLocation()
  const wide = pathname === '/' || pathname.startsWith('/kalender')
  return (
    <div className="relative min-h-dvh sm:flex">
      <LanguageSwitch />
      <nav
        aria-label={t('nav.main')}
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-rule bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:sticky sm:top-0 sm:h-dvh sm:w-52 sm:flex-col sm:border-t-0 sm:border-r sm:bg-transparent sm:px-4 sm:py-6 sm:pb-6"
      >
        <span className="mb-8 hidden px-2 font-display text-lg font-semibold tracking-[0.35em] text-ink sm:block">
          COMPASS
        </span>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              [
                item.more ? 'hidden sm:flex' : 'flex',
                'flex-1 flex-col items-center gap-0.5 py-2 text-[11px] sm:flex-none sm:flex-row sm:gap-3 sm:rounded-md sm:px-2 sm:py-2 sm:text-sm',
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
        <MoreMenu />
      </nav>
      <main className={`mx-auto w-full ${wide ? 'max-w-6xl' : 'max-w-3xl'} px-4 pt-16 pb-44 sm:px-10 sm:pt-10 sm:pb-16`}>
        <Outlet />
      </main>
    </div>
  )
}

export function SectionLabel({ children, count, tone }: { children: string; count?: number; tone?: 'signal' }) {
  return (
    <h2
      className={[
        'flex items-baseline gap-2 border-b border-rule pb-1 font-display text-[13px] font-semibold tracking-[0.18em] uppercase',
        tone === 'signal' ? 'text-signal' : 'text-muted',
      ].join(' ')}
    >
      {children}
      {count !== undefined && <span className="font-mono text-[11px] font-normal tracking-normal">{count}</span>}
    </h2>
  )
}
