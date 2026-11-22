import { Component, type ErrorInfo, type ReactNode } from 'react'

import { useI18n } from '../i18n/context'
import { button } from '../lib/ui'

interface Props {
  children: ReactNode
  fallback: (error: Error, reset: () => void) => ReactNode
}

interface State {
  error: Error | null
}

class Boundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return this.props.fallback(this.state.error, () => this.setState({ error: null }))
    }
    return this.props.children
  }
}

export function ErrorBoundary({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  return (
    <Boundary
      fallback={(error, reset) => (
        <div role="alert" className="mx-auto my-12 max-w-md rounded-xl border border-rule bg-paper-raised p-6">
          <h1 className="font-display text-lg font-semibold tracking-wide text-ink uppercase">
            {t('common.errorTitle')}
          </h1>
          <p className="mt-2 font-mono text-xs text-muted">{error.message}</p>
          <div className="mt-4 flex gap-2">
            <button type="button" onClick={reset} className={button('secondary')}>
              {t('common.retry')}
            </button>
            <button type="button" onClick={() => window.location.reload()} className={button('primary')}>
              {t('common.reload')}
            </button>
          </div>
        </div>
      )}
    >
      {children}
    </Boundary>
  )
}
