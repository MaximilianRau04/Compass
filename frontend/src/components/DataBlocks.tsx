import { useI18n } from '../i18n/context'

/* Building blocks shared by the data pages (training, sleep, nutrition). */

export function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-md border border-rule bg-paper-raised px-3 py-2.5">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold">{value}</p>
      {note && <p className="truncate font-mono text-[11px] text-muted">{note}</p>}
    </div>
  )
}

export function DataTable({ rows, head }: { rows: [string, string][]; head: [string, string] }) {
  const { t } = useI18n()
  return (
    <details className="mt-1 text-sm">
      <summary className="-my-2 cursor-pointer py-2 font-mono text-[11px] text-muted hover:text-ink">{t('training.table')}</summary>
      <table className="mt-2 w-full font-mono text-[12px] tabular-nums">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1 font-normal">{head[0]}</th>
            <th className="py-1 text-right font-normal">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b]) => (
            <tr key={a} className="border-t border-rule/60">
              <td className="py-1">{a}</td>
              <td className="py-1 text-right">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
