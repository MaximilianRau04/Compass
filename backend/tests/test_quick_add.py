from datetime import date, time

import pytest

from app.models.tasks import TaskPriority
from app.services.quick_add import parse_quick_add

# Thursday
TODAY = date(2026, 10, 15)
AREAS = {"uni": "uni", "arbeit": "arbeit", "privat": "privat", "projekte": "projekte"}


def parse(text: str):
    return parse_quick_add(text, TODAY, AREAS)


def test_example_from_plan():
    p = parse("morgen 14 Uhr Blatt 3 abgeben #uni !hoch")
    assert p.title == "Blatt 3 abgeben"
    assert p.due_date == date(2026, 10, 16)
    assert p.due_time == time(14, 0)
    assert p.area_slug == "uni"
    assert p.priority == TaskPriority.high
    assert p.scheduled_date is None


def test_plain_title_untouched():
    p = parse("Mails an Prof schreiben")
    assert p.title == "Mails an Prof schreiben"
    assert (p.due_date, p.scheduled_date, p.priority, p.area_slug) == (None, None, None, None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("heute", date(2026, 10, 15)),
        ("übermorgen", date(2026, 10, 17)),
        ("freitag", date(2026, 10, 16)),
        ("donnerstag", date(2026, 10, 15)),
        ("nächsten donnerstag", date(2026, 10, 22)),
        ("nächste woche", date(2026, 10, 19)),
        ("in 3 tagen", date(2026, 10, 18)),
        ("in einer woche", date(2026, 10, 22)),
        ("in 2 monaten", date(2026, 12, 15)),
        ("bis 20.10.", date(2026, 10, 20)),
        ("1.3.", date(2027, 3, 1)),
        ("12.11.2027", date(2027, 11, 12)),
        ("12. november", date(2026, 11, 12)),
        ("3 jan", date(2027, 1, 3)),
        ("2026-12-24", date(2026, 12, 24)),
    ],
)
def test_due_dates(text, expected):
    p = parse(f"Aufgabe {text}")
    assert p.title == "Aufgabe"
    assert p.due_date == expected


def test_scheduled_with_at_and_separate_deadline():
    p = parse("Literatur lesen @montag bis 30.10. #arbeit")
    assert p.title == "Literatur lesen"
    assert p.scheduled_date == date(2026, 10, 19)
    assert p.due_date == date(2026, 10, 30)
    assert p.area_slug == "arbeit"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("14:30", time(14, 30)),
        ("14.30 Uhr", time(14, 30)),
        ("um 9", time(9, 0)),
        ("8 uhr", time(8)),
    ],
)
def test_time_without_date_means_today(text, expected):
    p = parse(f"Anruf {text}")
    assert p.title == "Anruf"
    assert p.due_time == expected
    assert p.due_date == TODAY


@pytest.mark.parametrize(
    ("text", "rule", "first"),
    [
        ("jeden montag", "FREQ=WEEKLY;BYDAY=MO", date(2026, 10, 19)),
        ("montags", "FREQ=WEEKLY;BYDAY=MO", date(2026, 10, 19)),
        ("täglich", "FREQ=DAILY", TODAY),
        ("werktags", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", TODAY),
        ("alle 2 wochen", "FREQ=WEEKLY;INTERVAL=2", TODAY),
        ("monatlich", "FREQ=MONTHLY", TODAY),
    ],
)
def test_recurrence(text, rule, first):
    p = parse(f"Müll rausbringen {text} #privat")
    assert p.title == "Müll rausbringen"
    assert p.recurrence == rule
    assert p.scheduled_date == first
    assert p.due_date is None


def test_recurrence_with_explicit_deadline_keeps_deadline():
    p = parse("Report wöchentlich freitag")
    assert p.recurrence == "FREQ=WEEKLY"
    assert p.due_date == date(2026, 10, 16)
    assert p.scheduled_date is None


@pytest.mark.parametrize(
    ("token", "priority"),
    [
        ("!", TaskPriority.high),
        ("!!!", TaskPriority.urgent),
        ("!dringend", TaskPriority.urgent),
        ("!niedrig", TaskPriority.low),
    ],
)
def test_priority(token, priority):
    assert parse(f"Steuer {token}").priority == priority


def test_unknown_bang_word_stays_in_title():
    p = parse("Hallo !welt")
    assert p.title == "Hallo !welt"
    assert p.priority is None


def test_unknown_hashtag_becomes_tag_and_second_area_too():
    p = parse("Paper lesen #uni #arbeit #ki")
    assert p.area_slug == "uni"
    assert p.tags == ["arbeit", "ki"]


def test_numbers_in_title_are_not_dates():
    p = parse("Blatt 3 Aufgabe 2.1 rechnen")
    assert p.title == "Blatt 3 Aufgabe 2.1 rechnen"
    assert p.due_date is None


def test_invalid_date_is_ignored():
    p = parse("Termin 31.02.")
    assert p.due_date is None
    assert p.title == "Termin 31.02."


# --- English -------------------------------------------------------------------------------


def test_english_example():
    p = parse("tomorrow 2pm hand in sheet 3 #uni !high")
    assert p.title == "hand in sheet 3"
    assert p.due_date == date(2026, 10, 16)
    assert p.due_time == time(14, 0)
    assert p.area_slug == "uni"
    assert p.priority == TaskPriority.high


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("today", date(2026, 10, 15)),
        ("day after tomorrow", date(2026, 10, 17)),
        ("friday", date(2026, 10, 16)),
        ("next thursday", date(2026, 10, 22)),
        ("next week", date(2026, 10, 19)),
        ("in 3 days", date(2026, 10, 18)),
        ("in a week", date(2026, 10, 22)),
        ("by nov 12", date(2026, 11, 12)),
        ("on 3rd january", date(2027, 1, 3)),
        ("due may 5, 2027", date(2027, 5, 5)),
    ],
)
def test_english_due_dates(text, expected):
    p = parse(f"Task {text}")
    assert p.title == "Task"
    assert p.due_date == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2pm", time(14, 0)),
        ("9:30 am", time(9, 30)),
        ("12am", time(0, 0)),
        ("12pm", time(12, 0)),
        ("at 9", time(9, 0)),
        ("at 14:30", time(14, 30)),
    ],
)
def test_english_times(text, expected):
    p = parse(f"Call {text}")
    assert p.title == "Call"
    assert p.due_time == expected


def test_invalid_meridiem_time_is_ignored():
    p = parse("Room 13pm")
    assert p.due_time is None


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("every monday", "FREQ=WEEKLY;BYDAY=MO"),
        ("mondays", "FREQ=WEEKLY;BYDAY=MO"),
        ("daily", "FREQ=DAILY"),
        ("weekdays", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
        ("every 2 weeks", "FREQ=WEEKLY;INTERVAL=2"),
        ("monthly", "FREQ=MONTHLY"),
        ("yearly", "FREQ=YEARLY"),
    ],
)
def test_english_recurrence(text, rule):
    p = parse(f"Take out trash {text}")
    assert p.title == "Take out trash"
    assert p.recurrence == rule


def test_english_scheduled_and_mixed_languages():
    p = parse("@monday read papers bis 30.10. #arbeit !urgent")
    assert p.title == "read papers"
    assert p.scheduled_date == date(2026, 10, 19)
    assert p.due_date == date(2026, 10, 30)
    assert p.priority == TaskPriority.urgent
