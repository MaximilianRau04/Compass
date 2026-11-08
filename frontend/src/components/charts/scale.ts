/** Sizes, scales and the measured width shared by the charts. */

import { useLayoutEffect, useRef, useState } from 'react'

export const HEIGHT = 190

export const PAD = { top: 22, right: 16, bottom: 24, left: 44 }

// The line chart labels its last value to the right of the end marker.
export const LINE_RIGHT = 68

export function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    setWidth(el.clientWidth)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

/** Round tick values: 0, 5K, 10K … or 60, 70, 80. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (max <= min) max = min + 1
  const raw = (max - min) / count
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((f) => f * power).find((s) => s >= raw) ?? raw
  const start = Math.floor(min / step) * step
  const ticks = []
  for (let v = start; v <= max + step * 0.001; v += step) ticks.push(Math.round(v * 1000) / 1000)
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step)
  return ticks
}

/** Column with a 4px rounded data end and a square baseline. */
export function column(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h, w / 2)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}
