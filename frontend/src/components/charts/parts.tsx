/** Pieces several charts draw: the tooltip and the y axis. */

import { type ReactNode } from 'react'

import { PAD } from './scale'

export function Tooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  // Flip to the left of the pointer near the right edge so it never leaves the chart.
  const left = x > width - 170 ? undefined : x + 12
  const right = x > width - 170 ? width - x + 12 : undefined
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 rounded-md border border-rule bg-paper-raised px-2.5 py-1.5 text-xs whitespace-nowrap shadow-sm"
      style={{ left, right, top: Math.max(0, y - 12) }}
    >
      {children}
    </div>
  )
}

export function YAxis({ ticks, scale, right }: { ticks: number[]; scale: (v: number) => number; right: number }) {
  return (
    <g>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD.left} x2={right} y1={scale(tick)} y2={scale(tick)} stroke="var(--rule)" strokeWidth={1} />
          <text x={PAD.left - 8} y={scale(tick)} dy="0.32em" textAnchor="end" className="fill-muted font-mono text-3xs tabular-nums">
            {tick >= 1000 ? `${Math.round(tick / 100) / 10}K` : tick}
          </text>
        </g>
      ))}
    </g>
  )
}
