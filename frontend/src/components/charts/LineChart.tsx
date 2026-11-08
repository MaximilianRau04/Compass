import { type ReactNode, useState } from 'react'

import { Tooltip, YAxis } from './parts'
import { HEIGHT, LINE_RIGHT, niceTicks, PAD, useWidth } from './scale'

export interface LinePoint {
  key: string
  date: string
  value: number
}

/** One measure over time with a crosshair that snaps to the closest session. */
export function LineChart({
  data,
  tooltip,
  format,
  ariaLabel,
  dayLabel,
  gapDays,
  color = 'var(--chart)',
}: {
  data: LinePoint[]
  tooltip: (p: LinePoint) => ReactNode
  format: (value: number) => string
  ariaLabel: string
  /** Label days instead of months, for ranges of a few weeks. */
  dayLabel?: (date: string) => string
  /** Break the line where two points are further apart than this (no data in between). */
  gapDays?: number
  color?: string
}) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  if (data.length === 0) return <div ref={ref} />

  const times = data.map((p) => new Date(p.date).getTime())
  const t0 = times[0]
  const t1 = times[times.length - 1]
  const values = data.map((p) => p.value)
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = (hi - lo) * 0.1 || Math.max(hi * 0.1, 1)
  const ticks = niceTicks(Math.max(0, lo - pad), hi + pad)
  const innerW = Math.max(0, width - PAD.left - LINE_RIGHT)
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const x = (time: number) => PAD.left + (t1 === t0 ? innerW / 2 : ((time - t0) / (t1 - t0)) * innerW)
  const y = (v: number) => PAD.top + innerH - ((v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0])) * innerH
  const points = data.map((p, i) => [x(times[i]), y(p.value)] as const)
  // Segments between gaps; each gets its own line and area.
  const segments: (readonly [number, number])[][] = []
  points.forEach((point, i) => {
    const gap = gapDays !== undefined && i > 0 && times[i] - times[i - 1] > gapDays * 86_400_000
    if (i === 0 || gap) segments.push([])
    segments[segments.length - 1].push(point)
  })
  const line = segments.map((seg) => seg.map(([px, py], i) => `${i ? 'L' : 'M'}${px},${py}`).join('')).join('')
  const bottom = PAD.top + innerH
  const area = segments
    .map((seg) => `${seg.map(([px, py], i) => `${i ? 'L' : 'M'}${px},${py}`).join('')}L${seg[seg.length - 1][0]},${bottom}L${seg[0][0]},${bottom}Z`)
    .join('')
  const end = points[points.length - 1]

  const onMove = (event: React.PointerEvent<SVGRectElement>) => {
    const px = event.clientX - event.currentTarget.getBoundingClientRect().left + PAD.left
    let best = 0
    points.forEach(([qx], i) => {
      if (Math.abs(qx - px) < Math.abs(points[best][0] - px)) best = i
    })
    setHover(best)
  }
  const months = Array.from(new Set(data.map((p) => p.date.slice(0, 7))))
  const monthEvery = Math.max(1, Math.ceil(months.length / Math.max(1, Math.floor(innerW / 64))))

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
          <YAxis ticks={ticks} scale={y} right={PAD.left + innerW} />
          {dayLabel &&
            data.map((p, i) => {
              const every = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(innerW / 56))))
              if ((data.length - 1 - i) % every !== 0) return null
              return (
                <text key={p.key} x={points[i][0]} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-3xs">
                  {dayLabel(p.date)}
                </text>
              )
            })}
          {!dayLabel && months
            .filter((_, i) => i % monthEvery === 0)
            .map((month) => {
              const time = new Date(`${month}-01`).getTime()
              if (time < t0 || time > t1) return null
              return (
                <text key={month} x={x(time)} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-3xs">
                  {month.slice(5)}/{month.slice(2, 4)}
                </text>
              )
            })}
          <path d={area} fill={color} opacity={0.1} />
          <path d={line} pathLength={1} className="draw" fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {hover !== null && (
            <line x1={points[hover][0]} x2={points[hover][0]} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--muted)" strokeWidth={1} />
          )}
          {[hover ?? points.length - 1].map((i) => (
            <circle key={i} cx={points[i][0]} cy={points[i][1]} r={4.5} fill={color} stroke="var(--paper)" strokeWidth={2} />
          ))}
          <text x={end[0] + 8} y={end[1]} dy="0.32em" className="fill-ink font-mono text-2xs font-medium">
            {format(values[values.length - 1])}
          </text>
          <rect
            x={PAD.left}
            y={PAD.top}
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
        <Tooltip x={points[hover][0]} y={points[hover][1]} width={width}>
          {tooltip(data[hover])}
        </Tooltip>
      )}
    </div>
  )
}
