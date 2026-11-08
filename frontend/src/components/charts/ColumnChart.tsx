import { type ReactNode, useState } from 'react'

import { Tooltip, YAxis } from './parts'
import { column, HEIGHT, niceTicks, PAD, useWidth } from './scale'

export interface BarDatum {
  key: string
  value: number
  label: string
}

/** Columns over time, e.g. volume per week. The last column carries its value on the cap. */
export function ColumnChart({
  data,
  tooltip,
  format,
  ariaLabel,
  target,
  color = 'var(--chart)',
}: {
  data: BarDatum[]
  tooltip: (d: BarDatum) => ReactNode
  format: (value: number) => string
  ariaLabel: string
  /** Reference line, e.g. a daily goal. */
  target?: { value: number; label: string }
  color?: string
}) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...data.map((d) => d.value), target ? target.value * 1.05 : 0, 1)
  const ticks = niceTicks(0, max)
  const top = ticks[ticks.length - 1]
  const innerW = Math.max(0, width - PAD.left - PAD.right)
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const band = data.length ? innerW / data.length : 0
  const barW = Math.min(24, band * 0.6)
  const y = (v: number) => PAD.top + innerH - (v / top) * innerH
  const labelEvery = Math.max(1, Math.ceil(52 / Math.max(band, 1)))
  const last = data.length - 1

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
          <YAxis ticks={ticks} scale={y} right={width - PAD.right} />
          {data.map((d, i) => {
            const cx = PAD.left + band * i + band / 2
            const h = (d.value / top) * innerH
            return (
              <g key={d.key}>
                {h > 0 && (
                  <path
                    d={column(cx - barW / 2, y(d.value), barW, h)}
                    fill={color}
                    className="grow"
                    style={{ animationDelay: `${Math.min(i, 30) * 25}ms` }}
                    opacity={hover === null || hover === i ? 1 : 0.55}
                  />
                )}
                {(i % labelEvery === (last % labelEvery) || i === last) && (
                  <text x={cx} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-3xs">
                    {d.label}
                  </text>
                )}
                {i === last && d.value > 0 && (
                  <text x={cx} y={y(d.value) - 6} textAnchor="middle" className="fill-ink font-mono text-2xs font-medium">
                    {format(d.value)}
                  </text>
                )}
                {/* The whole band is the hit target, not just the thin column. */}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={innerH}
                  fill="transparent"
                  tabIndex={0}
                  aria-label={`${d.label}: ${format(d.value)}`}
                  onPointerEnter={() => setHover(i)}
                  onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  className="outline-none"
                />
              </g>
            )
          })}
          <line x1={PAD.left} x2={width - PAD.right} y1={y(0)} y2={y(0)} stroke="var(--muted)" strokeOpacity={0.5} strokeWidth={1} />
          {target && (
            <g className="pointer-events-none">
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(target.value)}
                y2={y(target.value)}
                stroke="var(--ink)"
                strokeOpacity={0.7}
                strokeWidth={1}
                strokeDasharray="4 3"
              />
              {/* A halo in the surface color keeps the label legible where it crosses columns. */}
              <text
                x={PAD.left + 4}
                y={y(target.value) - 5}
                stroke="var(--paper)"
                strokeWidth={3}
                paintOrder="stroke"
                className="fill-ink font-mono text-3xs"
              >
                {target.label}
              </text>
            </g>
          )}
        </svg>
      )}
      {hover !== null && (
        <Tooltip x={PAD.left + band * hover + band / 2} y={y(data[hover].value)} width={width}>
          {tooltip(data[hover])}
        </Tooltip>
      )}
    </div>
  )
}
