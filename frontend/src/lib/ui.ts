/*
 * Button styles, so every page uses the same four kinds:
 * primary (brass, the one main action), secondary (outlined), danger (outlined red, for
 * removing something) and quiet (text only, for minor actions next to others).
 */
const base = 'inline-flex items-center justify-center gap-1.5 rounded-md transition-colors disabled:pointer-events-none disabled:opacity-40'
const sizes = { sm: 'px-2.5 py-1 text-sm', md: 'px-3.5 py-2 text-sm', lg: 'px-5 py-2.5' }

export type ButtonKind = 'primary' | 'secondary' | 'danger' | 'quiet'

const kinds: Record<ButtonKind, string> = {
  primary: 'bg-brass font-medium text-brass-ink hover:brightness-105 active:brightness-95',
  secondary: 'border border-rule bg-paper-raised text-ink hover:border-ink',
  danger: 'border border-signal/45 text-signal hover:border-signal hover:bg-signal/10',
  quiet: 'text-muted hover:text-ink',
}

export const button = (kind: ButtonKind = 'secondary', size: keyof typeof sizes = 'md') => `${base} ${sizes[size]} ${kinds[kind]}`

/** The big heading at the top of every page. */
export const pageTitle = 'font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl'

/** The dimmed backdrop behind sheets and dialogs. */
export const overlay = 'fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]'
