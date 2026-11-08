import { type ReactNode, useLayoutEffect, useRef, useState } from 'react'

/* Small single-series SVG charts. Marks use the validated --chart color or the accent of the
 * measure (--m-*), text stays in ink and muted tokens, gridlines are hairlines in --rule. Every value is also reachable through the
 * tooltip and the table view the page renders next to the chart. */

const HEIGHT = 190
const PAD = { top: 22, right: 16, bottom: 24, left: 44 }
// The line chart labels its last value to the right of the end marker.
const LINE_RIGHT = 68

function useWidth() {
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
function niceTicks(min: number, max: number, count = 4): number[] {
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
function column(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h, w / 2)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

function Tooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
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

function YAxis({ ticks, scale, right }: { ticks: number[]; scale: (v: number) => number; right: number }) {
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
