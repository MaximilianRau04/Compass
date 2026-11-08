import { type ReactNode, useState } from 'react'

import { Tooltip } from './parts'
import { niceTicks, useWidth } from './scale'

export interface TimePoint {
  time: string
  value: number
}

const DAY_HEIGHT = 210

const DAY_PAD = { top: 18, right: 16, bottom: 24, left: 40 }

// A pause longer than this between two points is a gap (watch off), not a straight line.
const GAP_MS = 20 * 60_000

/** One measure over a day (e.g. heart rate): a crosshair snaps to the nearest point, a dashed
 * reference line marks a baseline (resting rate) and a shaded band a period (the night). */
export function DayCurve({
  points,
  start,
  end,
  reference,
  band,
  ariaLabel,
  tooltip,
  hourLabel,
  color = 'var(--chart)',
}: {
  points: TimePoint[]
  start: string
  end: string
  reference?: { value: number; label: string }
  band?: { start: string; end: string; label: string }
  ariaLabel: string
  tooltip: (p: TimePoint) => ReactNode
  hourLabel: (d: Date) => string
  color?: string
}) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const t0 = new Date(start).getTime()
  const t1 = new Date(end).getTime()
  const values = points.map((p) => p.value).concat(reference ? [reference.value] : [])
  const ticks = values.length ? niceTicks(Math.min(...values) - 5, Math.max(...values) + 5) : [40, 80, 120]
  const innerW = Math.max(0, width - DAY_PAD.left - DAY_PAD.right)
  const innerH = DAY_HEIGHT - DAY_PAD.top - DAY_PAD.bottom
  const x = (time: number) => DAY_PAD.left + ((time - t0) / (t1 - t0)) * innerW
  const y = (v: number) => DAY_PAD.top + innerH - ((v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0])) * innerH
  const times = points.map((p) => new Date(p.time).getTime())
  const xy = points.map((p, i) => [x(times[i]), y(p.value)] as const)
  const line = xy.map(([px, py], i) => `${i === 0 || times[i] - times[i - 1] > GAP_MS ? 'M' : 'L'}${px},${py}`).join('')
  const hourStep = innerW < 420 ? 6 : 3
  const hours = Array.from({ length: Math.floor(24 / hourStep) + 1 }, (_, i) => t0 + i * hourStep * 3_600_000).filter((t) => t <= t1)

  const onMove = (event: React.PointerEvent<SVGRectElement>) => {
    if (xy.length === 0) return
    const px = event.clientX - event.currentTarget.getBoundingClientRect().left + DAY_PAD.left
    let best = 0
    xy.forEach(([qx], i) => {
      if (Math.abs(qx - px) < Math.abs(xy[best][0] - px)) best = i
    })
    setHover(best)
  }

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${DAY_HEIGHT}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
          {band && (
            <g>
              <rect
                x={x(Math.max(t0, new Date(band.start).getTime()))}
                y={DAY_PAD.top}
                width={Math.max(0, x(Math.min(t1, new Date(band.end).getTime())) - x(Math.max(t0, new Date(band.start).getTime())))}
                height={innerH}
                fill="var(--rule)"
                opacity={0.45}
              />
              <text x={x(Math.max(t0, new Date(band.start).getTime())) + 6} y={DAY_PAD.top + 12} className="fill-muted font-mono text-3xs">
                {band.label}
              </text>
            </g>
          )}
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={DAY_PAD.left} x2={DAY_PAD.left + innerW} y1={y(tick)} y2={y(tick)} stroke="var(--rule)" strokeWidth={1} />
              <text x={DAY_PAD.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-muted font-mono text-3xs tabular-nums">
                {tick}
              </text>
            </g>
          ))}
          {hours.map((t) => (
            <text key={t} x={x(t)} y={DAY_HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-3xs">
              {hourLabel(new Date(t))}
            </text>
          ))}
          {reference && (
            <g>
              <line x1={DAY_PAD.left} x2={DAY_PAD.left + innerW} y1={y(reference.value)} y2={y(reference.value)} stroke="var(--muted)" strokeWidth={1} strokeDasharray="4 3" />
              <text x={DAY_PAD.left + innerW} y={y(reference.value) - 5} textAnchor="end" className="fill-muted font-mono text-3xs">
                {reference.label}
              </text>
            </g>
          )}
          <path d={line} pathLength={1} className="draw" fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {hover !== null && (
            <>
              <line x1={xy[hover][0]} x2={xy[hover][0]} y1={DAY_PAD.top} y2={DAY_PAD.top + innerH} stroke="var(--muted)" strokeWidth={1} />
              <circle cx={xy[hover][0]} cy={xy[hover][1]} r={4.5} fill={color} stroke="var(--paper)" strokeWidth={2} />
            </>
          )}
          <rect
            x={DAY_PAD.left}
            y={DAY_PAD.top}
            width={innerW}
            height={innerH}
            fill="transparent"
            onPointerMove={onMove}
            onPointerDown={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
      )}
      {hover !== null && (
        <Tooltip x={xy[hover][0]} y={xy[hover][1]} width={width}>
          {tooltip(points[hover])}
        </Tooltip>
      )}
    </div>
  )
}
