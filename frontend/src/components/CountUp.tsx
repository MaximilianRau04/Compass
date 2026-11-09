import { useEffect, useRef, useState } from 'react'

import { reducedMotion } from '../lib/preferences'

const DURATION = 700

/** A number that counts up to its value on mount, and from the old to the new value when it
 * changes. The final text is in the DOM from the start for screen readers. */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const still = reducedMotion()
  const [current, setShown] = useState(0)
  const shown = still ? value : current
  const from = useRef(0)

  useEffect(() => {
    if (still) return
    const start = performance.now()
    const origin = from.current
    let frame = 0
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / DURATION)
      const eased = 1 - (1 - p) ** 3
      const next = origin + (value - origin) * eased
      from.current = next
      setShown(next)
      if (p < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [value, still])

  return (
    <>
      <span aria-hidden>{format(Math.round(shown))}</span>
      <span className="sr-only">{format(value)}</span>
    </>
  )
}
