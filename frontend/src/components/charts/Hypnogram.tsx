import { type ReactNode, useState } from 'react'

import { Tooltip } from './parts'
import { PAD, useWidth } from './scale'

export interface HypnogramSegment {
  start: string
  end: string
  lane: number
}

const LANE_H = 30

const HYPNO_LEFT = 56

/** Sleep stages over one night: one lane per stage, awake on top, deep at the bottom. Position
 * carries the stage, so one color is enough; awake is drawn in muted ink as "not asleep". */
export function Hypnogram({
  segments,
  start,
  end,
  lanes,
  awakeLane,
  tooltip,
  hourLabel,
  ariaLabel,
  color = 'var(--chart)',
}: {
  segments: HypnogramSegment[]
  start: string
  end: string
  lanes: string[]
  awakeLane: number
  tooltip: (s: HypnogramSegment) => ReactNode
  hourLabel: (time: Date) => string
  ariaLabel: string
  color?: string
}) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const t0 = new Date(start).getTime()
  const t1 = Math.max(new Date(end).getTime(), t0 + 60_000)
  const top = 4
  const height = top + lanes.length * LANE_H + PAD.bottom
  const innerW = Math.max(0, width - HYPNO_LEFT - PAD.right)
  const x = (time: number) => HYPNO_LEFT + ((Math.min(Math.max(time, t0), t1) - t0) / (t1 - t0)) * innerW
  const laneY = (lane: number) => top + lane * LANE_H + LANE_H / 2
  const barH = 14

  const hourMs = 3_600_000
  const firstHour = Math.ceil(t0 / hourMs) * hourMs
  const hoursList: number[] = []
  for (let h = firstHour; h <= t1; h += hourMs) hoursList.push(h)
  const labelEvery = Math.max(1, Math.ceil(36 / Math.max(1, (innerW * hourMs) / (t1 - t0))))

  const geo = segments.map((s) => {
    const sx = x(new Date(s.start).getTime())
    const ex = x(new Date(s.end).getTime())
    return { ...s, sx, w: Math.max(1, ex - sx) }
  })

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full" role="img" aria-label={ariaLabel}>
          {lanes.map((label, i) => (
            <g key={label}>
              <line x1={HYPNO_LEFT} x2={width - PAD.right} y1={laneY(i)} y2={laneY(i)} stroke="var(--rule)" strokeWidth={1} />
              <text x={HYPNO_LEFT - 8} y={laneY(i)} dy="0.32em" textAnchor="end" className="fill-muted font-mono text-3xs">
                {label}
              </text>
            </g>
          ))}
          {hoursList.map((h, i) =>
            i % labelEvery === 0 ? (
              <text key={h} x={x(h)} y={height - 6} textAnchor="middle" className="fill-muted font-mono text-3xs tabular-nums">
                {hourLabel(new Date(h))}
              </text>
            ) : null,
          )}
          {/* Step connectors between consecutive stages, behind the bars. */}
          {geo.slice(1).map((s, i) => {
            const prev = geo[i]
            if (prev.lane === s.lane) return null
            return (
              <line
                key={`c${i}`}
                x1={s.sx}
                x2={s.sx}
                y1={laneY(prev.lane)}
                y2={laneY(s.lane)}
                stroke="var(--muted)"
                strokeOpacity={0.45}
                strokeWidth={1}
              />
            )
          })}
          {geo.map((s, i) => (
            <rect
              key={i}
              x={s.sx}
              y={laneY(s.lane) - barH / 2}
              width={s.w}
              height={barH}
              rx={Math.min(3, s.w / 2)}
              fill={s.lane === awakeLane ? 'var(--muted)' : color}
              opacity={hover === null || hover === i ? 1 : 0.55}
            />
          ))}
          {/* Hit targets: the full lane height around each segment, at least 6px wide. */}
          {geo.map((s, i) => (
            <rect
              key={`h${i}`}
              x={s.sx - Math.max(0, (6 - s.w) / 2)}
              y={laneY(s.lane) - LANE_H / 2}
              width={Math.max(6, s.w)}
              height={LANE_H}
              fill="transparent"
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onPointerDown={() => setHover(i)}
            />
          ))}
        </svg>
      )}
      {hover !== null && geo[hover] && (
        <Tooltip x={geo[hover].sx + geo[hover].w / 2} y={laneY(geo[hover].lane) - LANE_H / 2} width={width}>
          {tooltip(segments[hover])}
        </Tooltip>
      )}
    </div>
  )
}
