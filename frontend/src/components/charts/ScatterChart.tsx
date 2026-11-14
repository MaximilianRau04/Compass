import { useState } from 'react'

import { Tooltip, YAxis } from './parts'
import { HEIGHT, niceTicks, PAD, useWidth } from './scale'

export interface ScatterPoint {
  key: string
  x: number
  y: number
  label: string
}

/** One dot per day, x against y, with the least-squares line when there are enough points. */
export function ScatterChart({ points, xLabel, yLabel, format = (v) => String(v) }: { points: ScatterPoint[]; xLabel: string; yLabel: string; format?: (v: number) => string }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<ScatterPoint | null>(null)
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const xTicks = niceTicks(xs.length ? Math.min(...xs) : 0, xs.length ? Math.max(...xs) : 1)
  const yTicks = niceTicks(ys.length ? Math.min(...ys) : 0, ys.length ? Math.max(...ys) : 1)
  const right = Math.max(PAD.left + 1, width - PAD.right)
  const bottom = HEIGHT - PAD.bottom
  const x0 = xTicks[0]
  const x1 = xTicks[xTicks.length - 1]
  const y0 = yTicks[0]
  const y1 = yTicks[yTicks.length - 1]
  const sx = (v: number) => PAD.left + ((v - x0) / (x1 - x0 || 1)) * (right - PAD.left)
  const sy = (v: number) => bottom - ((v - y0) / (y1 - y0 || 1)) * (bottom - PAD.top)

  let fit: [number, number] | null = null
  if (points.length >= 10) {
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length
    const my = ys.reduce((a, b) => a + b, 0) / ys.length
    const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0)
    if (sxx > 0) {
      const slope = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0) / sxx
      fit = [slope, my - slope * mx]
    }
  }

  return (
    <div ref={ref} className="relative mt-2" onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-label={`${xLabel} / ${yLabel}`}>
          <YAxis ticks={yTicks} scale={sy} right={right} />
          {xTicks.map((tick) => (
            <text key={tick} x={sx(tick)} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-3xs tabular-nums">
              {tick >= 1000 ? `${Math.round(tick / 100) / 10}K` : tick}
            </text>
          ))}
          <text x={right} y={PAD.top - 8} textAnchor="end" className="fill-muted font-mono text-3xs">
            {xLabel} →
          </text>
          {fit && <line x1={sx(x0)} x2={sx(x1)} y1={sy(fit[0] * x0 + fit[1])} y2={sy(fit[0] * x1 + fit[1])} stroke="var(--muted)" strokeDasharray="4 4" strokeWidth={1} />}
          {points.map((p) => (
            <circle
              key={p.key}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={hover?.key === p.key ? 5 : 3.5}
              fill="var(--chart)"
              fillOpacity={0.7}
              onMouseEnter={() => setHover(p)}
              onClick={() => setHover(p)}
            />
          ))}
        </svg>
      )}
      {hover && (
        <Tooltip x={sx(hover.x)} y={sy(hover.y)} width={width}>
          <span className="font-mono text-muted">{hover.label}</span> {xLabel} {format(hover.x)} · {yLabel} {format(hover.y)}
        </Tooltip>
      )}
    </div>
  )
}
