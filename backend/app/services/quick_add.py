"""Parser for the quick-add syntax. German and English keywords both work, in any mix.

Examples:
    "morgen 14 Uhr Blatt 3 abgeben #study !hoch"
    "tomorrow 2pm hand in sheet 3 #study !high"
    "Müll rausbringen jeden Montag #privat" / "take out trash every monday #privat"
    "@freitag Literatur lesen #study" / "@friday read papers #study"

Rules:
    #name        area if a matching area exists, otherwise a tag
    !hoch        priority (!niedrig/!low, !hoch/!wichtig/!high, !dringend/!urgent, !, !!, !!!)
    <date>       due date (deadline): heute/today, morgen/tomorrow, übermorgen,
                 montag..sonntag / monday..sunday, nächsten freitag / next friday,
                 nächste woche / next week, in 3 tagen / in 3 days, 12.11., 12.11.2026,
                 12. november, nov 12, 2026-11-12. Optionally preceded by bis/am/fällig/by/on/due.
    @<date>      scheduled date (the day you want to work on it) instead of the deadline
    14 uhr, 14:30, 14.30 uhr, um 9, 2pm, 9:30 am, at 9
                 due time; without a date the task is due today
    täglich/daily, werktags/weekdays, wöchentlich/weekly, monatlich/monthly,
    jährlich/yearly, jeden montag/every monday, montags/mondays, alle 2 wochen/every 2 weeks
                 recurrence (RRULE); without a date the first occurrence is scheduled
"""

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from app.models.tasks import TaskPriority

WEEKDAYS = {
    "montag": 0,
    "dienstag": 1,
    "mittwoch": 2,
    "donnerstag": 3,
    "freitag": 4,
    "samstag": 5,
    "sonntag": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "mär": 3, "maerz": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11, "dezember": 12, "dez": 12,
    "january": 1, "february": 2, "march": 3, "mar": 3, "may": 5, "june": 6, "july": 7,
    "october": 10, "oct": 10, "december": 12, "dec": 12,
}  # fmt: skip
PRIORITY_WORDS = {
    "niedrig": TaskPriority.low,
    "low": TaskPriority.low,
    "normal": TaskPriority.normal,
    "hoch": TaskPriority.high,
    "wichtig": TaskPriority.high,
    "important": TaskPriority.high,
    "high": TaskPriority.high,
    "dringend": TaskPriority.urgent,
    "urgent": TaskPriority.urgent,
}
PRIORITY_BANGS = {1: TaskPriority.high, 2: TaskPriority.high, 3: TaskPriority.urgent}

WD = "|".join(WEEKDAYS)
MON = "|".join(sorted(MONTHS, key=len, reverse=True))
UNIT = r"(tag|tage|tagen|woche|wochen|monat|monate|monaten|day|days|week|weeks|month|months)"

FLAGS = re.IGNORECASE


@dataclass
class ParsedTask:
    title: str
    due_date: date | None = None
    due_time: time | None = None
    scheduled_date: date | None = None
    priority: TaskPriority | None = None
    area_slug: str | None = None
    tags: list[str] = field(default_factory=list)
    recurrence: str | None = None


def _next_weekday(today: date, weekday: int, *, strictly_after: bool = False) -> date:
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return today + timedelta(days=delta)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(d)


def _amount(word: str) -> int:
    words = {"einer": 1, "einem": 1, "zwei": 2, "drei": 3, "a": 1, "an": 1, "one": 1, "two": 2}
    return words.get(word.lower()) or int(word)


def _add(today: date, amount: int, unit: str) -> date:
    unit = unit.lower()
    if unit.startswith(("tag", "day")):
        return today + timedelta(days=amount)
    if unit.startswith(("woche", "week")):
        return today + timedelta(weeks=amount)
    return _add_months(today, amount)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _future_date(today: date, month: int, day: int, year: int | None) -> date | None:
    if year is not None:
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)
    candidate = _safe_date(today.year, month, day)
    if candidate and candidate < today:
        candidate = _safe_date(today.year + 1, month, day)
    return candidate


class _Text:
    """Holds the remaining text; matched tokens are cut out of it."""

    def __init__(self, text: str) -> None:
        self.text = f" {text} "

    def take(self, pattern: str, handler) -> None:
        def replace(match: re.Match) -> str:
            return " " if handler(match) is not False else match.group(0)

        self.text = re.sub(pattern, replace, self.text, flags=FLAGS)

    def take_first(self, pattern: str, handler) -> bool:
        for match in re.finditer(pattern, self.text, flags=FLAGS):
            if handler(match) is not False:
                self.text = self.text[: match.start()] + " " + self.text[match.end() :]
                return True
        return False

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", self.text).strip()


def _take_tags(rest: _Text, result: ParsedTask, area_slugs: dict[str, str]) -> None:
    """#name: the area if one matches (the first wins), otherwise a tag."""

    def hashtag(m: re.Match) -> None:
        word = m.group(1)
        slug = area_slugs.get(word.lower())
        if slug and result.area_slug is None:
            result.area_slug = slug
        elif word.lower() not in result.tags:
            result.tags.append(word.lower())

    rest.take(r"(?<!\S)#([\w-]+)", hashtag)


def _take_priority(rest: _Text, result: ParsedTask) -> None:
    """!, !!, !!! or !word."""

    def priority(m: re.Match) -> bool | None:
        bangs, word = m.group(1), m.group(2).lower()
        if word:
            if word not in PRIORITY_WORDS:
                return False
            result.priority = PRIORITY_WORDS[word]
        else:
            result.priority = PRIORITY_BANGS[len(bangs)]
        return None

    rest.take(r"(?<!\S)(!{1,3})(\w*)(?!\S)", priority)


def _take_recurrence(rest: _Text, result: ParsedTask, today: date) -> date | None:
    """The first recurrence found; returns its first occurrence."""
    first_occurrence: list[date] = []

    def recur(rule: str, first: date) -> None:
        result.recurrence = rule
        first_occurrence.append(first)

    def weekday_recur(m: re.Match) -> None:
        wd = WEEKDAYS[m.group(1).lower()]
        recur(f"FREQ=WEEKLY;BYDAY={RRULE_DAYS[wd]}", _next_weekday(today, wd))

    def interval_recur(m: re.Match) -> None:
        n, unit = int(m.group(1)), m.group(2).lower()
        freq = {"t": "DAILY", "d": "DAILY", "w": "WEEKLY"}.get(unit[0], "MONTHLY")
        recur(f"FREQ={freq};INTERVAL={n}", today)

    def workdays(_: re.Match) -> None:
        first = today if today.weekday() < 5 else _next_weekday(today, 0)
        recur("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", first)

    recurrences = [
        (rf"\b(?:jeden|every)\s+({WD})\b", weekday_recur),
        (rf"\b({WD})s\b", weekday_recur),
        (r"\b(?:alle|every)\s+(\d+)\s+(tage|wochen|monate|days|weeks|months)\b", interval_recur),
        (r"\b(werktags|jeden\s+werktag|weekdays|every\s+weekday)\b", workdays),
        (r"\b(täglich|jeden\s+tag|daily|every\s+day)\b", lambda m: recur("FREQ=DAILY", today)),
        (
            r"\b(wöchentlich|jede\s+woche|weekly|every\s+week)\b",
            lambda m: recur("FREQ=WEEKLY", today),
        ),
        (
            r"\b(monatlich|jeden\s+monat|monthly|every\s+month)\b",
            lambda m: recur("FREQ=MONTHLY", today),
        ),
        (
            r"\b(jährlich|jedes\s+jahr|yearly|annually|every\s+year)\b",
            lambda m: recur("FREQ=YEARLY", today),
        ),
    ]
    for pattern, handler in recurrences:
        if result.recurrence is None:
            rest.take_first(pattern, handler)
    return first_occurrence[0] if first_occurrence else None


def _take_time(rest: _Text, result: ParsedTask) -> None:
    """Times like "14 uhr", "14:30", "14.30 uhr", "um 9", "2pm", "9:30 am", "at 9"."""

    def set_time(m: re.Match) -> bool | None:
        groups = m.groupdict()
        hour, minute = int(m["h"]), int(groups.get("m") or 0)
        meridiem = (groups.get("ap") or "").lower()
        if meridiem:
            if not 1 <= hour <= 12:
                return False
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
        if hour > 23 or minute > 59:
            return False
        result.due_time = time(hour, minute)
        return None

    for pattern in (
        r"\b(?:um\s+)?(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*uhr\b",
        r"\b(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)\b",
        r"\b(?:um\s+|at\s+)?(?P<h>\d{1,2}):(?P<m>\d{2})\b",
        r"\b(?:um|at)\s+(?P<h>\d{1,2})\b(?![.:]\d)",
    ):
        if result.due_time is None:
            rest.take_first(pattern, set_time)


def _take_dates(rest: _Text, result: ParsedTask, today: date) -> None:
    """Dates. "@" marks the scheduled date, everything else is the deadline."""
    prefix = r"(?:(?<!\S)(?P<at>@)|\b(?:bis|am|fällig|by|on|due)\s+|\b)"

    def date_handler(compute):
        def handler(m: re.Match) -> bool | None:
            value = compute(m)
            if value is None:
                return False
            if m.group("at"):
                if result.scheduled_date is not None:
                    return False
                result.scheduled_date = value
            else:
                if result.due_date is not None:
                    return False
                result.due_date = value
            return None

        return handler

    dates = [
        (rf"{prefix}(?P<y>\d{{4}})-(?P<mo>\d{{2}})-(?P<d>\d{{2}})\b",
         lambda m: _safe_date(int(m["y"]), int(m["mo"]), int(m["d"]))),
        (rf"{prefix}(?P<d>\d{{1,2}})\.(?P<mo>\d{{1,2}})\.(?P<y>\d{{2,4}})?(?!\d)",
         lambda m: _future_date(today, int(m["mo"]), int(m["d"]), int(m["y"]) if m["y"] else None)),
        (rf"{prefix}(?P<d>\d{{1,2}})(?:\.|st|nd|rd|th)?\s*(?P<mon>{MON})\b\.?(?:\s+(?P<y>\d{{4}}))?",
         lambda m: _future_date(today, MONTHS[m["mon"].lower()], int(m["d"]),
                                int(m["y"]) if m["y"] else None)),
        (rf"{prefix}(?P<mon>{MON})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(?P<y>\d{{4}}))?",
         lambda m: _future_date(today, MONTHS[m["mon"].lower()], int(m["d"]),
                                int(m["y"]) if m["y"] else None)),
        (rf"{prefix}(?:übermorgen|day\s+after\s+tomorrow)\b", lambda m: today + timedelta(days=2)),
        (rf"{prefix}(?:morgen|tomorrow)\b", lambda m: today + timedelta(days=1)),
        (rf"{prefix}(?:heute|today)\b", lambda m: today),
        (rf"{prefix}in\s+(?P<n>\d+|einer|einem|zwei|drei|a|an|one|two)\s+{UNIT}\b",
         lambda m: _add(today, _amount(m["n"]), m[m.lastindex])),
        (rf"{prefix}(?:nächste\s+woche|next\s+week)\b",
         lambda m: _next_weekday(today, 0, strictly_after=True)),
        (rf"{prefix}(?:nächsten|next)\s+(?P<wd>{WD})\b",
         lambda m: _next_weekday(today, WEEKDAYS[m["wd"].lower()], strictly_after=True)),
        (rf"{prefix}(?P<wd>{WD})\b", lambda m: _next_weekday(today, WEEKDAYS[m["wd"].lower()])),
    ]  # fmt: skip
    for pattern, compute in dates:
        rest.take(pattern, date_handler(compute))


def parse_quick_add(text: str, today: date, area_slugs: dict[str, str]) -> ParsedTask:
    """Parse quick-add text.

    area_slugs maps lowercase slugs and names to the area slug, e.g. {"study": "study"}.
    Each step cuts what it understood out of the text; what is left becomes the title.
    """
    result = ParsedTask(title="")
    rest = _Text(text)
    _take_tags(rest, result, area_slugs)
    _take_priority(rest, result)
    # Without an explicit date, the first occurrence becomes the scheduled date.
    first_occurrence = _take_recurrence(rest, result, today)
    _take_time(rest, result)
    _take_dates(rest, result, today)

    if result.due_time and result.due_date is None:
        result.due_date = today
    if first_occurrence and result.due_date is None and result.scheduled_date is None:
        result.scheduled_date = first_occurrence

    result.title = rest.title
    return result
