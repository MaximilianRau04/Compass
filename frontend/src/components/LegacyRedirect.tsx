import { Navigate, useLocation } from 'react-router'

/** Sends an old path to its new one, keeping the query (e.g. the bank's ?code=…) and hash. */
export function LegacyRedirect({ to }: { to: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={`/${to}${search}${hash}`} replace />
}
