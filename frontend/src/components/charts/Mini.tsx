/** The small charts inside the body tiles. */

import { column, useWidth } from './scale'

/** Tiny trend for a stat tile: no axes, the tile names the measure and its page has the full
 * chart and table. Gaps (null) break the line. */
export function Sparkline({ values, ariaLabel, height = 36, color = 'var(--chart)' }: { values: (number | null)[]; ariaLabel: string; height?: number; color?: string }) {
  const [ref, width] = useWidth()
  const known = values.filter((v): v is number => v !== null)
  if (known.length < 2) return <div ref={ref} style={{ height }} />
  const lo = Math.min(...known)
  const hi = Math.max(...known)
  const pad = 4
  const x = (i: number) => pad + (i / (values.length - 1)) * (width - 2 * pad)
  const y = (v: number) => pad + (height - 2 * pad) * (hi === lo ? 0.5 : 1 - (v - lo) / (hi - lo))
  let d = ''
  values.forEach((v, i) => {
    if (v === null) return
    d += `${i === 0 || values[i - 1] === null ? 'M' : 'L'}${x(i)},${y(v)}`
  })
  const last = values.length - 1 - [...values].reverse().findIndex((v) => v !== null)
  return (
    <div ref={ref} style={{ height }}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} className="block h-full w-full" role="img" aria-label={ariaLabel}>
          <path d={d} pathLength={1} className="draw" fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={x(last)} cy={y(values[last]!)} r={4} fill={color} stroke="var(--paper-raised)" strokeWidth={2} />
        </svg>
      )}
    </div>
  )
}

/** Tiny columns for a stat tile, e.g. the last 7 days; the newest one is emphasised. */
export function MiniBars({
  values,
  ariaLabel,
  titles,
  height = 36,
  color = 'var(--chart)',
}: {
  values: (number | null)[]
  ariaLabel: string
  titles?: string[]
  height?: number
  color?: string
}) {
  const [ref, width] = useWidth()
  const max = Math.max(...values.map((v) => v ?? 0), 1)
  const gap = 2
  const w = values.length ? (width - gap * (values.length - 1)) / values.length : 0
  return (
    <div ref={ref} style={{ height }}>
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} className="block h-full w-full" role="img" aria-label={ariaLabel}>
          {values.map((v, i) => {
            const h = v ? Math.max(2, (v / max) * height) : 2
            const last = i === values.length - 1
            return (
              <path
                key={i}
                d={column(i * (w + gap), height - h, w, h)}
                fill={v ? color : 'var(--rule)'}
                opacity={v && !last ? 0.45 : 1}
                className="grow"
                style={{ animationDelay: `${150 + i * 45}ms` }}
              >
                {titles?.[i] && <title>{titles[i]}</title>}
              </path>
            )
          })}
        </svg>
      )}
    </div>
  )
}
