import { NavLink, Outlet } from 'react-router'

import { type Lang, useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'

const NAV: { to: string; label: MessageKey; icon: string }[] = [
  { to: '/', label: 'nav.today', icon: 'M12 3v2M12 19v2M3 12h2M19 12h2M12 8l2 4-2 4-2-4z' },
  { to: '/aufgaben', label: 'nav.tasks', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/training', label: 'nav.training', icon: 'M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12' },
]

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

export function Layout() {
  const { t } = useI18n()
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
                'flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] sm:flex-none sm:flex-row sm:gap-3 sm:rounded-md sm:px-2 sm:py-2 sm:text-sm',
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
      </nav>
      <main className="mx-auto w-full max-w-3xl px-4 pt-16 pb-44 sm:px-10 sm:pt-10 sm:pb-16">
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
