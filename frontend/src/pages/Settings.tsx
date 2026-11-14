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
import { FeedSettings } from '../components/FeedSettings'
import { SectionLabel } from '../components/Layout'
import { type Lang, useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import {
  type Accent,
  ACCENTS,
  type Motion,
  MOTIONS,
  type Page,
  PAGES,
  setPreference,
  TEXT_SIZES,
  type TextSize,
  type Theme,
  THEMES,
  type Units,
  UNITS,
  usePreferences,
} from '../lib/preferences'
import { button, pageTitle } from '../lib/ui'

const TOPICS: { topic: PushTopic; label: MessageKey; hint: MessageKey }[] = [
  { topic: 'bedtime', label: 'push.topic.bedtime', hint: 'push.topic.bedtimeHint' },
  { topic: 'deadlines', label: 'push.topic.deadlines', hint: 'push.topic.deadlinesHint' },
  { topic: 'resting', label: 'push.topic.resting', hint: 'push.topic.restingHint' },
  { topic: 'weekly', label: 'push.topic.weekly', hint: 'push.topic.weeklyHint' },
  { topic: 'finance', label: 'push.topic.finance', hint: 'push.topic.financeHint' },
  { topic: 'sync', label: 'push.topic.sync', hint: 'push.topic.syncHint' },
  { topic: 'claude', label: 'push.topic.claude', hint: 'push.topic.claudeHint' },
]

const BUTTON = button('secondary')

// Each language in its own name, so it can be found whatever is set.
const LANGUAGES: { value: Lang; label: string }[] = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
]

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return (
    <div role="group" aria-label={label} className="flex w-fit shrink-0 rounded-full border border-rule bg-paper-raised p-0.5 text-sm">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
          className={['rounded-full px-3 py-1 transition-colors', option.value === value ? 'bg-ink font-medium text-paper' : 'text-muted hover:text-ink'].join(' ')}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <span>
        <span className="block text-sm text-ink">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
      {children}
    </li>
  )
}

const PAGE_LIST = Object.entries(PAGES) as [Page, MessageKey][]

// The units by their symbols, which read the same in every language.
const UNIT_LABELS: Record<Units, string> = { metric: 'kg · cm · km', imperial: 'lb · in · mi' }

/** Round color fields for the accent, each in the shade of the current design. */
function AccentPicker({ value }: { value: Accent }) {
  const { t } = useI18n()
  return (
    <div className="flex shrink-0 items-center gap-3">
      <span className="text-sm text-muted">{t(`settings.accent.${value}`)}</span>
      <div role="group" aria-label={t('settings.accent')} className="flex gap-1.5">
        {ACCENTS.map((accent) => (
          <button
            key={accent}
            type="button"
            onClick={() => setPreference('accent', accent)}
            aria-pressed={accent === value}
            aria-label={t(`settings.accent.${accent}`)}
            title={t(`settings.accent.${accent}`)}
            className={['h-7 w-7 rounded-full border-2 transition-transform', accent === value ? 'scale-110 border-ink' : 'border-transparent hover:scale-110'].join(' ')}
            style={{ background: `var(--accent-${accent})` }}
          />
        ))}
      </div>
    </div>
  )
}

function Appearance() {
  const { lang, setLang, t } = useI18n()
  const prefs = usePreferences()
  return (
    <>
      <p className="mt-3 text-sm text-muted">{t('settings.appearanceHint')}</p>
      <ul className="mt-1 divide-y divide-rule/60">
        <Row label={t('lang.label')}>
          <Segmented label={t('lang.label')} value={lang} options={LANGUAGES} onChange={setLang} />
        </Row>
        <Row label={t('settings.theme')}>
          <Segmented<Theme>
            label={t('settings.theme')}
            value={prefs.theme}
            options={THEMES.map((value) => ({ value, label: t(`settings.theme.${value}`) }))}
            onChange={(value) => setPreference('theme', value)}
          />
        </Row>
        <Row label={t('settings.accent')}>
          <AccentPicker value={prefs.accent} />
        </Row>
        <Row label={t('settings.textSize')}>
          <Segmented<TextSize>
            label={t('settings.textSize')}
            value={prefs.textSize}
            options={TEXT_SIZES.map((value) => ({ value, label: t(`settings.textSize.${value}`) }))}
            onChange={(value) => setPreference('textSize', value)}
          />
        </Row>
        <Row label={t('settings.motion')} hint={t('settings.motionHint')}>
          <Segmented<Motion>
            label={t('settings.motion')}
            value={prefs.motion}
            options={MOTIONS.map((value) => ({ value, label: t(`settings.motion.${value}`) }))}
            onChange={(value) => setPreference('motion', value)}
          />
        </Row>
        <Row label={t('settings.units')} hint={t('settings.unitsHint')}>
          <Segmented<Units>
            label={t('settings.units')}
            value={prefs.units}
            options={UNITS.map((value) => ({ value, label: UNIT_LABELS[value] }))}
            onChange={(value) => setPreference('units', value)}
          />
        </Row>
      </ul>
    </>
  )
}

function Navigation() {
  const { t } = useI18n()
  const prefs = usePreferences()
  const toggle = (page: Page, shown: boolean) =>
    setPreference('hidden', shown ? prefs.hidden.filter((p) => p !== page) : [...prefs.hidden, page])
  return (
    <ul className="mt-1 divide-y divide-rule/60">
      <Row label={t('settings.start')} hint={t('settings.startHint')}>
        <select
          aria-label={t('settings.start')}
          value={prefs.start}
          onChange={(e) => setPreference('start', e.target.value as Page)}
          className="w-full rounded-md border border-rule bg-paper-raised px-3 py-1.5 text-sm text-ink focus:border-brass focus:outline-none sm:w-48"
        >
          {PAGE_LIST.map(([path, label]) => (
            <option key={path} value={path}>
              {t(label)}
            </option>
          ))}
        </select>
      </Row>
      <li className="py-3">
        <span className="block text-sm text-ink">{t('settings.pages')}</span>
        <span className="block text-xs text-muted">{t('settings.navigationHint')}</span>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
          {PAGE_LIST.map(([path, label]) => (
            <label key={path} className="flex cursor-pointer items-center gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                className="h-4 w-4 accent-brass"
                checked={!prefs.hidden.includes(path)}
                onChange={(e) => toggle(path, e.target.checked)}
              />
              {t(label)}
            </label>
          ))}
        </div>
      </li>
    </ul>
  )
}

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
          className={button('primary')}
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
      <p className="font-mono text-2xs text-muted">
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
        <h1 className={pageTitle}>{t('settings.title')}</h1>
      </header>
      <section className="mb-10">
        <SectionLabel>{t('settings.appearance')}</SectionLabel>
        <Appearance />
      </section>
      <section className="mb-10">
        <SectionLabel>{t('settings.navigation')}</SectionLabel>
        <Navigation />
      </section>
      <section>
        <SectionLabel>{t('push.title')}</SectionLabel>
        <div className="mt-3">
          <Notifications />
        </div>
      </section>
      <div className="mt-10">
        <FeedSettings />
      </div>
    </>
  )
}
