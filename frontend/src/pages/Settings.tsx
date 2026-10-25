import { toast } from 'sonner'

import {
  type PushTopic,
  sendTestPush,
  useDisablePush,
  useEnablePush,
  usePushConfig,
  usePushDevice,
  useSetPushTopics,
} from '../api/push'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'

const TOPICS: { topic: PushTopic; label: MessageKey; hint: MessageKey }[] = [
  { topic: 'bedtime', label: 'push.topic.bedtime', hint: 'push.topic.bedtimeHint' },
  { topic: 'deadlines', label: 'push.topic.deadlines', hint: 'push.topic.deadlinesHint' },
  { topic: 'resting', label: 'push.topic.resting', hint: 'push.topic.restingHint' },
  { topic: 'weekly', label: 'push.topic.weekly', hint: 'push.topic.weeklyHint' },
  { topic: 'finance', label: 'push.topic.finance', hint: 'push.topic.financeHint' },
  { topic: 'claude', label: 'push.topic.claude', hint: 'push.topic.claudeHint' },
]

const BUTTON = 'rounded-md border border-brass px-3 py-1.5 text-sm text-brass hover:bg-brass/10 disabled:opacity-50'

function Notifications() {
  const { t } = useI18n()
  const config = usePushConfig()
  const device = usePushDevice()
  const enable = useEnablePush()
  const disable = useDisablePush()
  const setTopics = useSetPushTopics()

  if (config.isPending || device.isPending) return <p className="font-mono text-sm text-muted">{t('common.loading')}</p>
  if (config.error) return <p className="text-signal">{config.error.message}</p>
  if (!config.data.enabled || !config.data.public_key) return <p className="max-w-lg text-sm text-muted">{t('push.notConfigured')}</p>

  const publicKey = config.data.public_key
  const state = device.data?.state ?? 'off'
  if (state === 'unsupported') return <p className="max-w-lg text-sm text-muted">{t('push.unsupported')}</p>
  if (state === 'denied') return <p className="max-w-lg text-sm text-signal">{t('push.denied')}</p>

  const current = device.data?.device
  if (state === 'off' || !current) {
    return (
      <div className="space-y-3">
        <p className="max-w-lg text-sm text-muted">{t('push.offHint')}</p>
        <button
          type="button"
          disabled={enable.isPending}
          className="rounded-md bg-brass px-3 py-2 text-sm font-medium text-brass-ink hover:opacity-90 disabled:opacity-50"
          onClick={() =>
            enable.mutate(publicKey, {
              onSuccess: (result) => toast(result ? t('push.enabled') : t('push.permissionRefused')),
              onError: (error) => toast.error(error.message),
            })
          }
        >
          {t('push.enable')}
        </button>
      </div>
    )
  }

  const toggle = (topic: PushTopic, on: boolean) => {
    const topics = on ? [...current.topics, topic] : current.topics.filter((x) => x !== topic)
    setTopics.mutate({ endpoint: current.endpoint, topics }, { onError: (error) => toast.error(error.message) })
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink">{t('push.onHint')}</p>
      <ul className="space-y-3">
        {TOPICS.map(({ topic, label, hint }) => (
          <li key={topic}>
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-brass"
                checked={current.topics.includes(topic)}
                disabled={setTopics.isPending}
                onChange={(e) => toggle(topic, e.target.checked)}
              />
              <span>
                <span className="block text-sm text-ink">{t(label)}</span>
                <span className="block text-xs text-muted">{t(hint)}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p className="font-mono text-[11px] text-muted">
        {t('push.quiet', { start: config.data.quiet_start, end: config.data.quiet_end })}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={BUTTON}
          onClick={() =>
            sendTestPush(current.endpoint).then(
              (r) => (r.sent ? toast(t('push.testSent')) : toast.error(t('push.testFailed'))),
              (error: Error) => toast.error(error.message),
            )
          }
        >
          {t('push.test')}
        </button>
        <button
          type="button"
          disabled={disable.isPending}
          className="rounded-md px-3 py-1.5 text-sm text-muted hover:text-signal disabled:opacity-50"
          onClick={() => disable.mutate(undefined, { onError: (error) => toast.error(error.message) })}
        >
          {t('push.disable')}
        </button>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const { t } = useI18n()
  return (
    <>
      <header className="mb-6">
        <h1 className="font-display text-5xl leading-none font-semibold tracking-tight uppercase sm:text-6xl">{t('settings.title')}</h1>
      </header>
      <section>
        <SectionLabel>{t('push.title')}</SectionLabel>
        <div className="mt-3">
          <Notifications />
        </div>
      </section>
    </>
  )
}
