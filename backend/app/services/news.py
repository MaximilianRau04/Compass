"""News ranking: the interest profile, thumbs as feedback, and trends across feeds.

No model is involved. An item's score is the sum of
- manual topics (a word or phrase from the profile) found in its title or summary,
- learned weights of the words in its title and of its feed, moved by the thumbs,
- a boost for words that are trending right now.

A word is trending when it shows up in at least TREND_MIN_FEEDS different feeds within
TREND_WINDOW_HOURS and clearly more often than in the days before. That way new tools appear
once several sources talk about them, even before anyone put them into the profile.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.news import NewsInterest, NewsItem
from app.services.clock import utc_now

TREND_WINDOW_HOURS = 36
TREND_BASELINE_DAYS = 14
TREND_MIN_FEEDS = 3
TREND_BOOST = 1.0
LEARN_RATE_TERM = 0.3
LEARN_RATE_FEED = 0.2
LEARNED_LIMIT = 3.0
FEED_LIMIT = 2.0
MAX_MANUAL = 100

WORD = re.compile(r"[^\W_](?:[\w+#.'-]*[\w+#])?")
STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has have how i if in
    into is it its just more most my new no not now of on or our out over so than that the their
    them then there these they this to up us was we were what when where which who why will with
    you your about after all also any back before being between both during each few get got
    here how's i'm it's let make many may might much must off once only other own same should
    some still such take through too under until very via vs want way well while would yet
    show ask hn launch use using used one two first last next year years day days week today
    pro plus says best top big better inside here's what's
    der die das den dem des ein eine einer eines einem einen und oder aber als auch auf aus bei
    bis für mit nach nicht noch nur ohne über um von vor wie wird werden wurde zu zum zur ist
    sind war hat haben kann können soll sollen muss im ins am an es er sie wir ihr ich man so
    was wer wo dass sich mehr neue neuer neues neuen jetzt heute gegen unter zwischen schon
    seit sein seine ihre ihren beim vom doch ab ja nein viele alle hier dort kommt gibt
    sagt laut wegen bald
    """.split()  # noqa: SIM905 (one long word list reads better as text)
)


def terms_of(title: str) -> list[str]:
    """Normalised words of a title, in order, without stopwords, numbers and duplicates."""
    out: list[str] = []
    for raw in WORD.findall(title.lower()):
        word = raw.strip(".'-")
        if (
            len(word) < 2
            or len(word) > 60
            or word in STOPWORDS
            or word.replace(".", "").replace(",", "").isdigit()
            or word in out
        ):
            continue
        out.append(word)
    return out[:30]


def normalise_topic(text: str) -> str:
    return " ".join(text.lower().split())[:80]


@dataclass
class Profile:
    manual: dict[str, float]
    learned: dict[str, float]
    _patterns: list[tuple[str, re.Pattern, float]] = field(default_factory=list)

    def __post_init__(self):
        self._patterns = [
            (topic, re.compile(rf"(?<!\w){re.escape(topic)}(?!\w)"), weight)
            for topic, weight in self.manual.items()
        ]

    def matches(self, item: NewsItem) -> list[tuple[str, float]]:
        text = f"{item.title} {item.summary or ''}".lower()
        return [(topic, w) for topic, pattern, w in self._patterns if pattern.search(text)]


def load_profile(session: Session) -> Profile:
    manual, learned = {}, {}
    for row in session.scalars(select(NewsInterest)):
        (manual if row.manual else learned)[row.term] = row.weight
    return Profile(manual=manual, learned=learned)


@dataclass
class Scored:
    item: NewsItem
    score: float
    topics: list[str]
    trending: list[str]


def score(item: NewsItem, profile: Profile, trending: set[str]) -> Scored:
    matched = profile.matches(item)
    value = sum(w for _, w in matched)
    value += sum(profile.learned.get(t, 0.0) for t in item.terms)
    value += profile.learned.get(f"feed:{item.feed}", 0.0)
    hot = [t for t in item.terms if t in trending]
    value += min(len(hot), 2) * TREND_BOOST
    if item.feedback:
        value += 5.0 * item.feedback
    return Scored(item=item, score=round(value, 2), topics=[t for t, _ in matched], trending=hot)


# --- Trends ------------------------------------------------------------------------------------


@dataclass
class Trend:
    term: str
    feeds: list[str]
    count: int


def trends(session: Session, now: datetime | None = None, limit: int = 10) -> list[Trend]:
    now = now or utc_now()
    window_start = now - timedelta(hours=TREND_WINDOW_HOURS)
    baseline_start = now - timedelta(days=TREND_BASELINE_DAYS)
    rows = session.execute(
        select(NewsItem.feed, NewsItem.terms, NewsItem.published_at).where(
            NewsItem.published_at >= baseline_start, NewsItem.published_at <= now
        )
    )
    recent_feeds: dict[str, set[str]] = defaultdict(set)
    recent_count: dict[str, int] = defaultdict(int)
    baseline_count: dict[str, int] = defaultdict(int)
    for feed, terms, published in rows:
        for term in set(terms):
            if published >= window_start:
                recent_feeds[term].add(feed)
                recent_count[term] += 1
            else:
                baseline_count[term] += 1
    windows = (TREND_BASELINE_DAYS * 24 - TREND_WINDOW_HOURS) / TREND_WINDOW_HOURS
    out = []
    for term, feeds in recent_feeds.items():
        if len(feeds) < TREND_MIN_FEEDS:
            continue
        usual = baseline_count[term] / windows
        if recent_count[term] >= 3 * (usual + 0.5):
            out.append(Trend(term=term, feeds=sorted(feeds), count=recent_count[term]))
    out.sort(key=lambda t: (-len(t.feeds), -t.count, t.term))
    return out[:limit]


# --- Reading -----------------------------------------------------------------------------------


def ranked(
    session: Session,
    hours: int = 36,
    stream: str | None = None,
    include_disliked: bool = True,
    limit: int = 100,
) -> list[Scored]:
    """Items of the last `hours`, best first. General items keep their feed order (newest
    first) unless the profile says something about them."""
    stmt = select(NewsItem).where(NewsItem.published_at >= utc_now() - timedelta(hours=hours))
    if stream:
        stmt = stmt.where(NewsItem.stream == stream)
    if not include_disliked:
        stmt = stmt.where(NewsItem.feedback.is_distinct_from(-1))
    items = list(session.scalars(stmt))
    profile = load_profile(session)
    hot = {t.term for t in trends(session)}
    scored = [score(i, profile, hot) for i in items]
    scored.sort(key=lambda s: (-s.score, -s.item.published_at.timestamp()))
    return scored[:limit]


def get_item(session: Session, item_id: int) -> NewsItem:
    item = session.get(NewsItem, item_id)
    if item is None:
        raise ValueError("news item not found")
    return item


# --- Feedback and profile ----------------------------------------------------------------------


def _learn(session: Session, term: str, delta: float, limit: float) -> None:
    row = session.get(NewsInterest, (term, False))
    if row is None:
        row = NewsInterest(term=term, manual=False, weight=0.0)
        session.add(row)
    row.weight = max(-limit, min(limit, round(row.weight + delta, 3)))


def set_feedback(session: Session, item: NewsItem, value: int | None) -> None:
    """Thumbs up (1), down (-1) or take it back (None). The learned weights move by the
    difference, so changing your mind does not count twice."""
    if value not in (1, -1, None):
        raise ValueError("feedback must be 1, -1 or empty")
    delta = (value or 0) - (item.feedback or 0)
    item.feedback = value
    if delta:
        for term in item.terms:
            _learn(session, term, LEARN_RATE_TERM * delta, LEARNED_LIMIT)
        _learn(session, f"feed:{item.feed}", LEARN_RATE_FEED * delta, FEED_LIMIT)
    session.flush()


def manual_interests(session: Session) -> list[NewsInterest]:
    return list(
        session.scalars(
            select(NewsInterest)
            .where(NewsInterest.manual.is_(True))
            .order_by(NewsInterest.weight.desc(), NewsInterest.term)
        )
    )


def learned_interests(session: Session, limit: int = 20) -> tuple[list, list]:
    """The strongest learned likes and dislikes."""
    rows = list(session.scalars(select(NewsInterest).where(NewsInterest.manual.is_(False))))
    likes = sorted((r for r in rows if r.weight > 0), key=lambda r: -r.weight)[:limit]
    dislikes = sorted((r for r in rows if r.weight < 0), key=lambda r: r.weight)[:limit]
    return likes, dislikes


def replace_manual(session: Session, topics: dict[str, float]) -> list[NewsInterest]:
    """Replace the manual topics. Weight 0 drops a topic."""
    cleaned: dict[str, float] = {}
    for topic, weight in topics.items():
        key = normalise_topic(topic)
        if key and weight:
            cleaned[key] = max(-5.0, min(5.0, float(weight)))
    if len(cleaned) > MAX_MANUAL:
        raise ValueError(f"at most {MAX_MANUAL} topics")
    for row in manual_interests(session):
        if row.term in cleaned:
            row.weight = cleaned.pop(row.term)
        else:
            session.delete(row)
    for topic, weight in cleaned.items():
        session.add(NewsInterest(term=topic, manual=True, weight=weight))
    session.flush()
    return manual_interests(session)


def reset_learned(session: Session) -> None:
    session.execute(delete(NewsInterest).where(NewsInterest.manual.is_(False)))
    session.flush()
