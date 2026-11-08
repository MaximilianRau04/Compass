import { useState } from 'react'
import { toast } from 'sonner'

import { useInterests, useNews, useNewsFeedback, useNewsOverview, useResetLearned, useSaveInterests, useSyncNews } from '../api/news'
import { useTodayDate } from '../api/tasks'
import type { Interest, Interests, NewsItem, NewsOverview } from '../api/types'
import { SectionLabel } from '../components/Layout'
import { Markdown } from '../components/Markdown'
import { SyncIssue } from '../components/SyncIssue'
import { useI18n } from '../i18n/context'
import { clockTime, decimal, localDay, pill, relativeDay } from '../lib/format'
import { button, pageTitle } from '../lib/ui'

type Stream = 'personal' | 'general'
const RANGES = [36, 72, 168] as const
const PAGE = 15

function Thumb({ item, value }: { item: NewsItem; value: 1 | -1 }) {
  const { t } = useI18n()
  const feedback = useNewsFeedback()
  const active = item.feedback === value
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={value === 1 ? t('news.like') : t('news.dislike')}
      title={value === 1 ? t('news.like') : t('news.dislike')}
      disabled={feedback.isPending}
      onClick={() => feedback.mutate({ id: item.id, value: active ? null : value }, { onError: (error) => toast.error(error.message) })}
      className={[
        "relative rounded-md border px-2 py-0.5 text-sm transition-colors disabled:opacity-50 before:absolute before:-inset-y-1.5 before:inset-x-0 before:content-['']",
        active ? (value === 1 ? 'border-brass bg-brass/10 text-brass' : 'border-signal bg-signal/10 text-signal') : 'border-rule text-muted hover:border-ink hover:text-ink',
      ].join(' ')}
    >
      <svg viewBox="0 0 24 24" className={`h-4 w-4 ${value === -1 ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
        <path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

function NewsRow({ item, today, onTopic }: { item: NewsItem; today: string; onTopic: (term: string) => void }) {
  const { t, locale } = useI18n()
  return (
    <li className={`py-3 ${item.feedback === -1 ? 'opacity-50' : ''}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <a href={item.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium hover:text-brass">
            {item.title}
          </a>
          <p className="mt-0.5 font-mono text-[11px] text-muted">
            {item.feed} · {relativeDay(localDay(item.published_at), today, t, locale)} {clockTime(item.published_at, locale)}
            {item.score !== 0 && ` · ${item.score > 0 ? '+' : ''}${decimal(item.score, locale)}`}
          </p>
          {item.summary && <p className="mt-1 line-clamp-2 text-sm text-muted">{item.summary}</p>}
          {(item.topics.length > 0 || item.trending.length > 0) && (
            <p className="mt-1.5 flex flex-wrap gap-1">
              {item.topics.map((topic) => (
                <button key={topic} type="button" onClick={() => onTopic(topic)} className="rounded-full border border-rule px-2 py-0.5 text-[11px] text-muted hover:border-ink hover:text-ink">
                  {topic}
                </button>
              ))}
              {item.trending.map((term) => (
                <button key={term} type="button" onClick={() => onTopic(term)} className="rounded-full border border-brass/60 px-2 py-0.5 text-[11px] text-brass hover:bg-brass/10">
                  ↗ {term}
                </button>
              ))}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <Thumb item={item} value={1} />
          <Thumb item={item} value={-1} />
        </div>
      </div>
    </li>
  )
}

function Feeds({ overview, today }: { overview: NewsOverview; today: string }) {
  const { t, locale } = useI18n()
  const failed = overview.feeds.filter((f) => f.last_error)
  const last = overview.feeds.map((f) => f.last_success_at).filter((v): v is string => !!v).sort().at(-1)
  return (
    <div className="mb-6 font-mono text-[11px] text-muted">
      <p>
        {t('news.feeds', { n: overview.feeds.length })}
        {last && ` · ${t('news.fetchedAt', { when: `${relativeDay(localDay(last), today, t, locale)} ${clockTime(last, locale)}` })}`}
      </p>
      {failed.map((f) => (
        <SyncIssue key={f.feed} name={f.feed} error={f.last_error!} lastSuccess={f.last_success_at} today={today} />
      ))}
    </div>
  )
}

/** The summary of the most important news: the main content of the page. */
function Report({ overview, today }: { overview: NewsOverview; today: string }) {
  const { t, locale } = useI18n()
  const report = overview.report
  if (!report) {
    return (
      <section className="rounded-lg border border-dashed border-rule px-4 py-5">
        <p className="font-medium">{t('news.noReportTitle')}</p>
        <p className="mt-1 max-w-xl text-sm text-muted">{t('news.noReport')}</p>
      </section>
    )
  }
  const old = report.local_date < today
  return (
    <section className="rounded-lg border border-rule bg-paper-raised px-4 py-4 sm:px-6 sm:py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-display text-[13px] font-semibold tracking-[0.18em] text-muted uppercase">{report.title ?? t('news.report')}</h2>
        <span className={`font-mono text-[11px] ${old ? 'text-brass' : 'text-muted'}`}>
          {t('news.reportBy', { date: relativeDay(report.local_date, today, t, locale) })}
          {old && ` · ${t('news.reportOld')}`}
        </span>
      </div>
      <Markdown text={report.body} className="mt-3" />
    </section>
  )
}

function TopicEditor({ interests }: { interests: Interests }) {
  const { t, locale } = useI18n()
  const save = useSaveInterests()
  const reset = useResetLearned()
  const [topics, setTopics] = useState<Interest[]>(interests.topics)
  const [term, setTerm] = useState('')
  const [weight, setWeight] = useState('1')
  const dirty = JSON.stringify(topics) !== JSON.stringify(interests.topics)

  const add = () => {
    const value = Number(weight.replace(',', '.'))
    const key = term.trim().toLowerCase()
    if (!key || !Number.isFinite(value) || value === 0) return
    setTopics([...topics.filter((x) => x.term !== key), { term: key, weight: value }])
    setTerm('')
  }

  const learned = (rows: Interest[]) => rows.map((r) => `${r.term} ${r.weight > 0 ? '+' : ''}${decimal(r.weight, locale)}`).join(', ')

  return (
    <details className="text-sm">
      <summary className="cursor-pointer list-none">
        <SectionLabel count={topics.length}>{t('news.profile')}</SectionLabel>
      </summary>
      <p className="mt-2 max-w-xl text-muted">{t('news.profileHint')}</p>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {topics.map((topic) => (
          <li key={topic.term} className={`flex items-center gap-1 rounded-full border py-0.5 pr-1 pl-2.5 ${topic.weight < 0 ? 'border-signal/60 text-signal' : 'border-rule'}`}>
            {topic.term}
            <span className="font-mono text-[11px] text-muted">
              {topic.weight > 0 ? '+' : ''}
              {decimal(topic.weight, locale)}
            </span>
            <button type="button" aria-label={t('news.removeTopic', { term: topic.term })} onClick={() => setTopics(topics.filter((x) => x.term !== topic.term))} className="relative rounded-full px-1.5 text-muted hover:text-ink before:absolute before:-inset-x-1 before:-inset-y-1.5 before:content-['']">
              ×
            </button>
          </li>
        ))}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          add()
        }}
      >
        <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder={t('news.topicPlaceholder')} aria-label={t('news.topic')} className="min-w-0 flex-1 rounded-md border border-rule bg-paper-raised px-2 py-1.5" />
        <input value={weight} onChange={(e) => setWeight(e.target.value)} inputMode="decimal" aria-label={t('news.weight')} className="w-16 rounded-md border border-rule bg-paper-raised px-2 py-1.5 font-mono" />
        <button type="submit" className={button('secondary')}>
          {t('news.addTopic')}
        </button>
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(topics, { onSuccess: () => toast(t('news.saved')), onError: (error) => toast.error(error.message) })}
          className={button('primary')}
        >
          {t('news.save')}
        </button>
      </form>
      <p className="mt-2 font-mono text-[11px] text-muted">{t('news.weightHint')}</p>

      <div className="mt-4 space-y-1 text-muted">
        <p>
          <span className="text-ink">{t('news.likes')}:</span> {learned(interests.likes) || '–'}
        </p>
        <p>
          <span className="text-ink">{t('news.dislikes')}:</span> {learned(interests.dislikes) || '–'}
        </p>
        {(interests.likes.length > 0 || interests.dislikes.length > 0) && (
          <button type="button" disabled={reset.isPending} onClick={() => reset.mutate(undefined, { onSuccess: () => toast(t('news.resetDone')) })} className={`mt-1 ${button('secondary', 'sm')}`}>
            {t('news.reset')}
          </button>
        )}
      </div>
    </details>
  )
}

export function NewsPage() {
  const { t } = useI18n()
  const today = useTodayDate()
  const [stream, setStream] = useState<Stream>('personal')
  const [hours, setHours] = useState<number>(36)
  const [feed, setFeed] = useState<string>('')
  const [topic, setTopic] = useState<string | null>(null)
  const [relevant, setRelevant] = useState(true)
  const [shown, setShown] = useState(PAGE)
  const overview = useNewsOverview()
  const news = useNews({ hours, stream })
  const interests = useInterests()
  const sync = useSyncNews()

  const header = (
    <header className="mb-2 flex flex-wrap items-end justify-between gap-3">
      <h1 className={pageTitle}>{t('news.title')}</h1>
      <button
        type="button"
        disabled={sync.isPending}
        onClick={() =>
          sync.mutate(undefined, {
            onSuccess: (result) => {
              const created = Object.values(result).reduce<number>((n, r) => n + (typeof r === 'object' && r && 'new' in r ? Number(r.new) : 0), 0)
              toast(t('news.fetched', { n: created }))
            },
            onError: (error) => toast.error(error.message),
          })
        }
        className={button('primary')}
      >
        {sync.isPending ? t('news.fetching') : t('news.fetch')}
      </button>
    </header>
  )

  if (overview.error || news.error) {
    return <>{header}<p className="text-signal">{t('news.loadError', { message: (overview.error ?? news.error)!.message })}</p></>
  }
  if (overview.isPending || news.isPending) return <>{header}<p className="font-mono text-sm text-muted">{t('common.loading')}</p></>

  const feeds = overview.data.feeds.filter((f) => f.stream === stream).map((f) => f.feed)
  const filtered = news.data.filter(
    (item) =>
      (!feed || item.feed === feed) &&
      (!topic || item.topics.includes(topic) || item.trending.includes(topic)) &&
      // "Relevant" only applies to the personal stream: items the profile or a thumb likes.
      (stream === 'general' || !relevant || topic !== null || item.score > 0 || item.feedback === 1),
  )
  const pickTopic = (term: string) => {
    setTopic(topic === term ? null : term)
    setShown(PAGE)
  }
  const switchStream = (next: Stream) => {
    setStream(next)
    setFeed('')
    setShown(PAGE)
  }

  return (
    <>
      {header}
      <Feeds overview={overview.data} today={today} />

      <div className="space-y-8">
        <Report overview={overview.data} today={today} />

        {/* The single items are the material of the report; folded away while there is one. */}
        <details open={!overview.data.report} className="space-y-8">
          <summary className="cursor-pointer list-none">
            <SectionLabel count={news.data.length}>{t('news.allItems')}</SectionLabel>
          </summary>
          <div className="mt-4 space-y-8">
        {overview.data.trends.length > 0 && (
          <section>
            <SectionLabel count={overview.data.trends.length}>{t('news.trends')}</SectionLabel>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {overview.data.trends.slice(0, 8).map((trend) => (
                <li key={trend.term}>
                  <button
                    type="button"
                    title={trend.feeds.join(', ')}
                    aria-pressed={topic === trend.term}
                    onClick={() => pickTopic(trend.term)}
                    className={['rounded-full border px-2.5 py-0.5 text-sm', topic === trend.term ? 'border-brass bg-brass text-brass-ink' : 'border-brass/60 text-brass hover:bg-brass/10'].join(' ')}
                  >
                    ↗ {trend.term} <span className="font-mono text-[11px] opacity-70">{t('news.trendFeeds', { n: trend.feeds.length })}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {(['personal', 'general'] as Stream[]).map((s) => (
              <button key={s} type="button" className={pill(stream === s)} aria-pressed={stream === s} onClick={() => switchStream(s)}>
                {t(s === 'personal' ? 'news.personal' : 'news.general')}
              </button>
            ))}
            <span className="ml-auto flex gap-1.5">
              {RANGES.map((h) => (
                <button key={h} type="button" className={pill(hours === h)} aria-pressed={hours === h} onClick={() => { setHours(h); setShown(PAGE) }}>
                  {h < 48 ? `${h} h` : t('news.days', { n: h / 24 })}
                </button>
              ))}
            </span>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <select value={feed} onChange={(e) => { setFeed(e.target.value); setShown(PAGE) }} aria-label={t('news.source')} className="rounded-md border border-rule bg-paper-raised px-2 py-1">
              <option value="">{t('news.allSources')}</option>
              {feeds.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            {stream === 'personal' && (
              <label className="flex items-center gap-1.5 text-muted">
                <input type="checkbox" checked={relevant} onChange={(e) => { setRelevant(e.target.checked); setShown(PAGE) }} className="accent-brass" />
                {t('news.onlyRelevant')}
              </label>
            )}
            {topic && (
              <button type="button" onClick={() => pickTopic(topic)} className="rounded-full border border-ink bg-ink px-2.5 py-0.5 text-paper">
                {topic} ×
              </button>
            )}
            <span className="ml-auto font-mono text-[11px] text-muted">{t('news.count', { n: filtered.length, total: news.data.length })}</span>
          </div>
          {filtered.length === 0 ? (
            <p className="text-muted">{overview.data.feeds.length === 0 ? t('news.empty') : t('news.nothing')}</p>
          ) : (
            <>
              <ul className="divide-y divide-rule/60">
                {filtered.slice(0, shown).map((item) => (
                  <NewsRow key={item.id} item={item} today={today} onTopic={pickTopic} />
                ))}
              </ul>
              {filtered.length > shown && (
                <button type="button" onClick={() => setShown(shown + PAGE)} className={`mt-3 w-full ${button('secondary')}`}>
                  {t('news.more', { n: Math.min(PAGE, filtered.length - shown) })}
                </button>
              )}
            </>
          )}
        </section>
          </div>
        </details>

        {interests.data && <TopicEditor key={JSON.stringify(interests.data.topics)} interests={interests.data} />}
        <p className="max-w-xl text-sm text-muted">{t('news.hint')}</p>
      </div>
    </>
  )
}
