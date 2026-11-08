import * as Dialog from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'

import { useI18n } from '../i18n/context'
import { button, overlay } from '../lib/ui'

/** A small question before something that cannot be undone, e.g. throwing away a workout. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirm,
  onConfirm,
  danger = true,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  confirm: string
  onConfirm: () => void
  danger?: boolean
}) {
  const { t } = useI18n()
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 z-50 w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-rule bg-paper-raised p-5 shadow-xl"
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <Dialog.Title className="font-display text-xl font-semibold tracking-wide uppercase">{title}</Dialog.Title>
          {description && <Dialog.Description className="mt-2 text-sm text-muted">{description}</Dialog.Description>}
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close className={button('quiet')}>{t('common.cancel')}</Dialog.Close>
            <button
              type="button"
              autoFocus
              onClick={() => {
                onConfirm()
                onOpenChange(false)
              }}
              className={danger ? `${button('danger')} bg-signal/10` : button('primary')}
            >
              {confirm}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
