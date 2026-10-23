import * as Dialog from '@radix-ui/react-dialog'

import type { CalendarEvent } from '../../api/types'
import { useI18n } from '../../i18n/context'
import { eventTime, localDay, longDate } from '../../lib/format'
import { useEventStyle } from './eventStyle'

/** Details of a calendar entry. Read-only: entries come from the subscribed calendars. */
export function EventSheet({ event, onClose }: { event: CalendarEvent | null; onClose: () => void }) {
  const { t, locale } = useI18n()
  const style = useEventStyle()
  return (
    <Dialog.Root open={event !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border border-rule bg-paper-raised p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:w-[26rem] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-2xl">
          {event && (
            <>
              <Dialog.Title className="flex items-start gap-3 font-display text-2xl leading-tight font-semibold">
                <span className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${style(event).dot}`} />
                {event.title}
              </Dialog.Title>
              <Dialog.Description asChild>
                <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  <dt className="font-mono text-[11px] tracking-wide text-muted uppercase">{t('cal.when')}</dt>
                  <dd>
                    {(() => {
                      const { weekday, date } = longDate(localDay(event.starts_at), locale)
                      return `${weekday}, ${date} · ${eventTime(event, t, locale)}`
                    })()}
                  </dd>
                  {event.location && (
                    <>
                      <dt className="font-mono text-[11px] tracking-wide text-muted uppercase">{t('cal.where')}</dt>
                      <dd>{event.location}</dd>
                    </>
                  )}
                  <dt className="font-mono text-[11px] tracking-wide text-muted uppercase">{t('cal.source')}</dt>
                  <dd className="uppercase">{event.feed}</dd>
                </dl>
              </Dialog.Description>
              <div className="mt-6 flex justify-end">
                <Dialog.Close className="rounded-full border border-rule px-4 py-1.5 text-sm text-muted hover:border-ink hover:text-ink">
                  {t('sheet.close')}
                </Dialog.Close>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
