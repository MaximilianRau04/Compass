from datetime import timedelta

from app.ingestion import calendar
from app.models.health import DailyMetrics
from app.services import analysis, nutrition
from app.services.clock import local_today
from tests.test_calendar import ics, stamp, vevent
from tests.test_healthconnect import at, ingest, iso, record

TODAY = local_today()


def sleep(id, wake_day, bed_day_offset, bed, wake):
    """A night without stages from `bed` (on the day before or the wake day) to `wake`."""
    bed_at = at(wake_day - timedelta(days=bed_day_offset), bed)
    return record(id, "sleep", bed_at, at(wake_day, wake), stages=[])


def test_bedtimes_around_midnight_and_short_and_early_nights(session):
    d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
    ingest(
        session,
        [
            sleep("n1", d(3), 1, "23:30", "07:30"),  # 8 h
            sleep("n2", d(2), 0, "00:30", "06:30"),  # 6 h, before an early lecture
            sleep("n3", d(1), 0, "00:00", "08:00"),  # 8 h
        ],
    )
    calendar.sync_feed(session, "campus", ics(vevent("l", "Vorlesung", stamp(d(2), "0800"))), TODAY)
    c = analysis.sleep_consistency(session, 7)
    assert (c.nights, c.median_bedtime, c.median_wake_time) == (3, "00:00", "07:30")
    assert c.bedtime_sd_minutes == 24  # 23:30, 00:00, 00:30 counted from noon: -30, 0, +30
    assert c.short_nights == [d(2)]
    [early] = c.early_nights
    assert (early.date, early.first_event, early.asleep_minutes) == (d(2), "08:00", 360)
    assert (c.avg_asleep_early, c.avg_asleep_other) == (360, 480)


def test_resting_heart_rate_alert(session):
    for i in range(30):
        bpm = 63 if i < 5 else 55
        session.add(
            DailyMetrics(
                local_date=TODAY - timedelta(days=i), resting_hr=bpm, updated_at=at(TODAY, "08:00")
            )
        )
    session.flush()
    r = analysis.resting_trend(session, 30)
    assert r.median == 55
    assert r.latest_mean7 == round((63 * 5 + 55 * 2) / 7, 1)
    assert r.alert


def test_zone2_minutes_cap_gaps(session):
    start = at(TODAY, "10:00")
    samples = [
        {"time": iso(start + timedelta(minutes=m)), "bpm": bpm}
        for m, bpm in [(0, 100), (1, 115), (2, 120), (3, 140), (4, 118), (60, 118)]
    ]
    ingest(
        session, [record("hr", "heart_rate", start, start + timedelta(minutes=61), samples=samples)]
    )
    # HRmax 178: zone 2 is 107-125. 115, 120 count a minute each; 118 at 04:00 counts 5 minutes
    # (the gap to the next sample is capped), 118 at 01:00 later counts to the week's end, capped.
    weeks = analysis.zone2_weeks(session, 1)
    assert weeks[-1].minutes == 12
    nutrition.set_goal(session, "hr_max", 200)  # zone 2 is now 120-140
    assert analysis.zone2_weeks(session, 1)[-1].minutes == 2


def test_latest_bedtime_before_the_first_event(client, session):
    tomorrow = TODAY + timedelta(days=1)
    calendar.sync_feed(
        session,
        "campus",
        ics(
            vevent("m", "Blockkurs", stamp(tomorrow, "0000"), stamp(tomorrow, "0000")),
            vevent("a", "Vorlesung", stamp(tomorrow, "0800")),
            vevent("b", "Mittag", stamp(tomorrow, "1200")),
            vevent("c", "Feiertag", f"VALUE=DATE:{tomorrow:%Y%m%d}"),
        ),
        TODAY,
    )
    b = analysis.bedtime_for(session, tomorrow)
    # Up at 06:00, 7.5 h of sleep and 30 min to fall asleep before that; the 00:00 marker
    # without a duration is no appointment.
    assert (b.title, f"{b.wake_at:%H:%M}", f"{b.latest_bedtime:%H:%M}") == (
        "Vorlesung",
        "06:00",
        "22:00",
    )
    assert b.latest_bedtime.date() == TODAY
    data = client.get("/api/sleep/bedtime").json()
    assert data["event"]["title"] == "Vorlesung" and data["latest_bedtime"].startswith(
        f"{TODAY}T22:00"
    )
    assert analysis.bedtime_for(session, tomorrow + timedelta(days=1)) is None
