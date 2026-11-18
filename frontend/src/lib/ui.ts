/* One restrained action treatment across pages; chart colors are not button colors. */
const base = 'inline-flex min-h-9 items-center justify-center gap-1.5 rounded-md border font-medium transition-[background-color,border-color,color] duration-150 disabled:pointer-events-none disabled:opacity-40'
const sizes = { sm: 'px-2.5 py-1 text-sm', md: 'px-3.5 py-2 text-sm', lg: 'px-5 py-2.5' }

export type ButtonKind = 'primary' | 'secondary' | 'danger' | 'quiet'

const kinds: Record<ButtonKind, string> = {
  primary: 'border-brass bg-brass text-brass-ink hover:opacity-90 active:opacity-80',
  secondary: 'border-rule bg-paper-raised text-ink hover:border-muted hover:bg-paper',
  danger: 'border-signal/45 bg-transparent text-signal hover:border-signal hover:bg-signal/10',
  quiet: 'border-transparent bg-transparent text-muted hover:bg-ink/5 hover:text-ink',
}

export const button = (kind: ButtonKind = 'secondary', size: keyof typeof sizes = 'md') => `${base} ${sizes[size]} ${kinds[kind]}`

/** The big heading at the top of every page. */
export const pageTitle = 'text-3xl leading-tight font-semibold tracking-tight sm:text-4xl'

/** The dimmed backdrop behind sheets and dialogs. */
export const overlay = 'fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]'
