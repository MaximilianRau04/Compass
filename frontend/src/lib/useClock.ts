import { useEffect, useState } from 'react'

/** Current device time, refreshed every minute and whenever the app becomes visible again. */
export function useDeviceNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const refresh = () => setNow(new Date())
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    const timer = window.setInterval(refresh, 60_000)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('focus', refresh)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('focus', refresh)
    }
  }, [])
  return now
}
