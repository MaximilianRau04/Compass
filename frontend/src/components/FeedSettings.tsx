import { useState } from 'react'
import { toast } from 'sonner'

import { type Feed, type FeedKind, type NewsStream, useAddCalendarFeed, useAddNewsFeed, useFeeds, useRemoveFeed, useRestoreFeed } from '../api/feeds'
import { useAreas } from '../api/tasks'
import { useI18n } from '../i18n/context'
import { button } from '../lib/ui'
import { SectionLabel } from './Layout'

const INPUT = 'w-full min-w-0 rounded-md border border-rule bg-paper-raised px-3 py-1.5 focus:border-brass focus:outline-none'
const SUBMIT = button('secondary')
const ROW_BUTTON = `shrink-0 ${button('secondary', 'sm')}`

/** The same rule as the names of .env: they key the events and items of a feed. */
const feedName = (label: string) =>
  label
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)

function FeedRow({ kind, feed }: { kind: FeedKind; feed: Feed }) {
  const { t } = useI18n()
  const remove = useRemoveFeed()
  const restore = useRestoreFeed()
  const [sure, setSure] = useState(false)
  const target = { kind, name: feed.name }
  const onError = (error: Error) => toast.error(error.message)

  return (
    <li className="flex items-center justify-between gap-3 py-2 text-sm">
      <span className={`min-w-0 ${feed.hidden ? 'text-muted' : ''}`}>
        <span className="font-medium">{feed.name}</span>
        <span className="block truncate font-mono text-[11px] text-muted">
          {[feed.host, feed.stream && t(feed.stream === 'general' ? 'feeds.general' : 'feeds.personal'), feed.area, feed.origin === 'env' && '.env']
            .filter(Boolean)
            .join(' · ')}
        </span>
      </span>
      {feed.hidden ? (
        <button type="button" disabled={restore.isPending} className={ROW_BUTTON} onClick={() => restore.mutate(target, { onError })}>
          {t('feeds.restore')}
        </button>
      ) : (
        <button
          type="button"
          disabled={remove.isPending}
          className={ROW_BUTTON}
          onBlur={() => setSure(false)}
          onClick={() => (sure ? remove.mutate(target, { onError }) : setSure(true))}
        >
          {t(sure ? 'feeds.removeSure' : 'feeds.remove')}
        </button>
      )}
    </li>
  )
}

function AddCalendar() {
  const { t } = useI18n()
  const add = useAddCalendarFeed()
  const areas = useAreas()
  const [label, setLabel] = useState('')
  const [url, setUrl] = useState('')
  const [area, setArea] = useState('')
  const [pattern, setPattern] = useState('')
  const name = feedName(label)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    add.mutate(
      { name, url, area: area || null, deadline_pattern: pattern || null },
      {
        onSuccess: () => {
          setLabel('')
          setUrl('')
          setArea('')
          setPattern('')
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <input aria-label={t('feeds.name')} placeholder={t('feeds.name')} className={INPUT} value={label} onChange={(e) => setLabel(e.target.value)} />
      <input aria-label={t('feeds.calendarUrl')} placeholder={t('feeds.calendarUrl')} inputMode="url" autoComplete="off" className={INPUT} value={url} onChange={(e) => setUrl(e.target.value)} />
      <select aria-label={t('feeds.area')} className={INPUT} value={area} onChange={(e) => setArea(e.target.value)}>
        <option value="">{t('feeds.noArea')}</option>
        {(areas.data ?? []).map((a) => (
          <option key={a.id} value={a.slug}>
            {a.name}
          </option>
        ))}
      </select>
      <details className="text-sm text-muted">
        <summary className="cursor-pointer">{t('feeds.deadlines')}</summary>
        <p className="my-2">{t('feeds.deadlinesHint')}</p>
        <input aria-label={t('feeds.deadlines')} placeholder=" is due$" className={`${INPUT} font-mono text-ink`} value={pattern} onChange={(e) => setPattern(e.target.value)} />
      </details>
      <button type="submit" disabled={!name || !url.trim() || add.isPending} className={SUBMIT}>
        {t(add.isPending ? 'feeds.checking' : 'feeds.add')}
      </button>
    </form>
  )
}

function AddNews() {
  const { t } = useI18n()
  const add = useAddNewsFeed()
  const [label, setLabel] = useState('')
  const [url, setUrl] = useState('')
  const [stream, setStream] = useState<NewsStream>('personal')
  const name = feedName(label)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    add.mutate(
      { name, url, stream },
      {
        onSuccess: () => {
          setLabel('')
          setUrl('')
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <input aria-label={t('feeds.name')} placeholder={t('feeds.name')} className={INPUT} value={label} onChange={(e) => setLabel(e.target.value)} />
      <input aria-label={t('feeds.newsUrl')} placeholder={t('feeds.newsUrl')} inputMode="url" autoComplete="off" className={INPUT} value={url} onChange={(e) => setUrl(e.target.value)} />
      <select aria-label={t('feeds.stream')} className={INPUT} value={stream} onChange={(e) => setStream(e.target.value as NewsStream)}>
        <option value="personal">{t('feeds.personal')}</option>
        <option value="general">{t('feeds.general')}</option>
      </select>
      <button type="submit" disabled={!name || !url.trim() || add.isPending} className={SUBMIT}>
        {t(add.isPending ? 'feeds.checking' : 'feeds.add')}
      </button>
    </form>
  )
}

/** Calendars and news feeds. Those from .env are listed too: they can be hidden, not edited. */
export function FeedSettings() {
  const { t } = useI18n()
  const feeds = useFeeds()

  if (feeds.error) return <p className="text-signal">{feeds.error.message}</p>
  if (feeds.isPending) return <p className="font-mono text-sm text-muted">{t('common.loading')}</p>

  return (
    <div className="max-w-lg space-y-8">
      {feeds.data.config_error && <p className="text-sm text-signal">{t('feeds.configError', { error: feeds.data.config_error })}</p>}
      <section className="space-y-3">
        <SectionLabel>{t('feeds.calendars')}</SectionLabel>
        <p className="text-sm text-muted">{t('feeds.calendarsHint')}</p>
        {feeds.data.calendars.length > 0 && (
          <ul className="divide-y divide-rule/60">
            {feeds.data.calendars.map((feed) => (
              <FeedRow key={feed.name} kind="calendar" feed={feed} />
            ))}
          </ul>
        )}
        <AddCalendar />
      </section>
      <section className="space-y-3">
        <SectionLabel>{t('feeds.news')}</SectionLabel>
        <p className="text-sm text-muted">{t('feeds.newsHint')}</p>
        {feeds.data.news.length > 0 && (
          <ul className="divide-y divide-rule/60">
            {feeds.data.news.map((feed) => (
              <FeedRow key={feed.name} kind="news" feed={feed} />
            ))}
          </ul>
        )}
        <AddNews />
      </section>
    </div>
  )
}
