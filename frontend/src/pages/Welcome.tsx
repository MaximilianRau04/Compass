import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { type SetupSource, useFinishSetup, useSetup } from '../api/setup'
import { useAreas, useCreateArea, useUpdateArea } from '../api/tasks'
import type { Area } from '../api/types'
import { FeedSettings } from '../components/FeedSettings'
import { SectionLabel } from '../components/Layout'
import { useI18n } from '../i18n/context'
import type { MessageKey } from '../i18n/messages'
import { AREA_BG } from '../lib/format'
import { button, pageTitle } from '../lib/ui'

const INPUT = 'min-w-0 flex-1 rounded-md border border-rule bg-paper-raised px-3 py-1.5 focus:border-brass focus:outline-none'

const SOURCES: { source: SetupSource; label: MessageKey; hint: MessageKey }[] = [
  { source: 'calendars', label: 'welcome.source.calendars', hint: 'welcome.source.calendarsHint' },
  { source: 'health', label: 'welcome.source.health', hint: 'welcome.source.healthHint' },
  { source: 'mail', label: 'welcome.source.mail', hint: 'welcome.source.mailHint' },
  { source: 'news', label: 'welcome.source.news', hint: 'welcome.source.newsHint' },
  { source: 'finance', label: 'welcome.source.finance', hint: 'welcome.source.financeHint' },
  { source: 'push', label: 'welcome.source.push', hint: 'welcome.source.pushHint' },
]

const slugOf = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)

function AreaRow({ area }: { area: Area }) {
  const { t } = useI18n()
  const update = useUpdateArea()
  const [name, setName] = useState(area.name)
  const onError = (error: Error) => toast.error(error.message)
  const rename = () => {
    const next = name.trim()
    if (next && next !== area.name) update.mutate({ id: area.id, name: next }, { onError })
    else setName(area.name)
  }
  return (
    <li className="flex items-center gap-2">
      <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${AREA_BG[area.color] ?? AREA_BG.slate}`} />
      <input aria-label={t('welcome.areaName')} className={INPUT} value={name} onChange={(e) => setName(e.target.value)} onBlur={rename} />
      <button
        type="button"
        className={button('secondary', 'sm')}
        onClick={() => update.mutate({ id: area.id, archived: true }, { onError })}
      >
        {t('welcome.areaRemove')}
      </button>
    </li>
  )
}

function Areas() {
  const { t } = useI18n()
  const areas = useAreas()
  const create = useCreateArea()
  const [name, setName] = useState('')
  const list = areas.data ?? []
  const slug = slugOf(name)

  const add = (event: React.FormEvent) => {
    event.preventDefault()
    if (!slug) return
    const colors = Object.keys(AREA_BG)
    create.mutate(
      { slug, name: name.trim(), color: colors[list.length % colors.length], sort_order: (list.length + 1) * 10 },
      { onSuccess: () => setName(''), onError: (error) => toast.error(error.message) },
    )
  }

  return (
    <section className="space-y-3">
      <SectionLabel>{t('welcome.areas')}</SectionLabel>
      <p className="max-w-lg text-sm text-muted">{t('welcome.areasHint')}</p>
      <ul className="max-w-lg space-y-2">
        {list.map((area) => (
          <AreaRow key={area.id} area={area} />
        ))}
      </ul>
      <form onSubmit={add} className="flex max-w-lg gap-2">
        <input aria-label={t('welcome.areaNew')} placeholder={t('welcome.areaNew')} className={INPUT} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" disabled={!slug || create.isPending} className={button('secondary')}>
          {t('welcome.areaAdd')}
        </button>
      </form>
    </section>
  )
}

/** The first start of an empty install: language and time, areas, and what is set up so far. */
export function WelcomePage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const setup = useSetup()
  const finish = useFinishSetup()

  if (setup.error) return <p className="text-signal">{setup.error.message}</p>
  if (setup.isPending) return <p className="font-mono text-sm text-muted">{t('common.loading')}</p>
  const { sources, timezone, language } = setup.data

  return (
    <div className="space-y-8">
      <header>
        <h1 className={pageTitle}>{t('welcome.title')}</h1>
        <p className="mt-4 max-w-lg text-muted">{t('welcome.intro')}</p>
      </header>

      <section className="space-y-3">
        <SectionLabel>{t('welcome.basics')}</SectionLabel>
        <dl className="max-w-lg space-y-2 text-sm">
          <div>
            <dt className="font-medium">{t('welcome.language')}</dt>
            <dd className="text-muted">{t('welcome.languageHint', { language: language.toUpperCase() })}</dd>
          </div>
          <div>
            <dt className="font-medium">{t('welcome.timezone', { timezone })}</dt>
            <dd className="text-muted">{t('welcome.timezoneHint')}</dd>
          </div>
        </dl>
      </section>

      <Areas />

      <section className="space-y-3">
        <SectionLabel>{t('welcome.sources')}</SectionLabel>
        <p className="max-w-lg text-sm text-muted">{t('welcome.sourcesHint')}</p>
        <ul className="max-w-lg divide-y divide-rule/60">
          {SOURCES.map(({ source, label, hint }) => (
            <li key={source} className="flex items-baseline justify-between gap-4 py-2 text-sm">
              <span>
                <span className="font-medium">{t(label)}</span>
                <span className="block text-muted">{t(hint)}</span>
              </span>
              <span className={`shrink-0 font-mono text-[11px] ${sources[source] ? 'text-chart' : 'text-muted'}`}>
                {t(sources[source] ? 'welcome.on' : 'welcome.off')}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <FeedSettings />

      <button
        type="button"
        disabled={finish.isPending}
        className={button('primary', 'lg')}
        onClick={() =>
          finish.mutate(undefined, {
            onSuccess: () => navigate('/', { replace: true }),
            onError: (error) => toast.error(error.message),
          })
        }
      >
        {t('welcome.start')}
      </button>
    </div>
  )
}
