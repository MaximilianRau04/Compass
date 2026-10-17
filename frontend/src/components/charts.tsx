import { type ReactNode, useLayoutEffect, useRef, useState } from 'react'

/* Small single-series SVG charts. Marks use the validated --chart color, text stays in ink and
 * muted tokens, gridlines are hairlines in --rule. Every value is also reachable through the
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
          <text x={PAD.left - 8} y={scale(tick)} dy="0.32em" textAnchor="end" className="fill-muted font-mono text-[10px] tabular-nums">
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
}: {
  data: BarDatum[]
  tooltip: (d: BarDatum) => ReactNode
  format: (value: number) => string
  ariaLabel: string
}) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...data.map((d) => d.value), 1)
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
                    fill="var(--chart)"
                    opacity={hover === null || hover === i ? 1 : 0.55}
                  />
                )}
                {(i % labelEvery === (last % labelEvery) || i === last) && (
                  <text x={cx} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-[10px]">
                    {d.label}
                  </text>
                )}
                {i === last && d.value > 0 && (
                  <text x={cx} y={y(d.value) - 6} textAnchor="middle" className="fill-ink font-mono text-[11px] font-medium">
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
}: {
  data: LinePoint[]
  tooltip: (p: LinePoint) => ReactNode
  format: (value: number) => string
  ariaLabel: string
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
  const line = points.map(([px, py], i) => `${i ? 'L' : 'M'}${px},${py}`).join('')
  const area = `${line}L${points[points.length - 1][0]},${PAD.top + innerH}L${points[0][0]},${PAD.top + innerH}Z`
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
          {months
            .filter((_, i) => i % monthEvery === 0)
            .map((month) => {
              const time = new Date(`${month}-01`).getTime()
              if (time < t0 || time > t1) return null
              return (
                <text key={month} x={x(time)} y={HEIGHT - 6} textAnchor="middle" className="fill-muted font-mono text-[10px]">
                  {month.slice(5)}/{month.slice(2, 4)}
                </text>
              )
            })}
          <path d={area} fill="var(--chart)" opacity={0.1} />
          <path d={line} fill="none" stroke="var(--chart)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {hover !== null && (
            <line x1={points[hover][0]} x2={points[hover][0]} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--muted)" strokeWidth={1} />
          )}
          {[hover ?? points.length - 1].map((i) => (
            <circle key={i} cx={points[i][0]} cy={points[i][1]} r={4.5} fill="var(--chart)" stroke="var(--paper)" strokeWidth={2} />
          ))}
          <text x={end[0] + 8} y={end[1]} dy="0.32em" className="fill-ink font-mono text-[11px] font-medium">
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
