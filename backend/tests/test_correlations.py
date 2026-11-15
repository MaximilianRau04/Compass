from datetime import date, timedelta

import pytest

from app.services import correlations, journal
from app.services.clock import local_today
from app.services.daily import DayRow

START = date(2026, 1, 1)


def rows(values):
    out = []
    for i, (sleep, mood) in enumerate(values):
        r = DayRow(START + timedelta(days=i))
        r.asleep_minutes = sleep
        r.mood = mood
        out.append(r)
    return out


def test_pearson_needs_enough_days():
    assert correlations.pearson([1.0] * 3, [2.0] * 3) is None
    xs = [float(i) for i in range(12)]
    assert correlations.pearson(xs, [2 * x + 1 for x in xs]) == 1.0
    assert correlations.pearson(xs, [-x for x in xs]) == -1.0
    assert correlations.pearson(xs, [5.0] * 12) is None


def test_days_without_a_value_are_left_out():
    data = [(420 + 10 * i, 1 + i % 5) for i in range(12)] + [(None, 3), (480, None)]
    c = correlations.correlate(rows(data), "sleep", "mood")
    assert c.n == 12 and c.r is not None


def test_lag_reads_y_days_later():
    data = [(60 * i, i) for i in range(12)]
    c = correlations.correlate(rows(data), "sleep", "mood", lag=1)
    assert c.n == 11
    assert c.points[0] == (START, 0.0, 1.0)


def test_unknown_values_and_lags_are_refused():
    with pytest.raises(correlations.CorrelationError):
        correlations.correlate([], "sleep", "luck")
    with pytest.raises(correlations.CorrelationError):
        correlations.correlate([], "sleep", "mood", lag=8)


def test_correlations_api(client, session):
    journal.save(session, local_today() - timedelta(days=2), mood=4, energy=3)
    session.commit()
    listed = client.get("/api/correlations").json()
    assert len(listed) == len(correlations.PRESETS)
    assert all(c["points"] == [] for c in listed)
    pair = client.get("/api/correlations/pair", params={"x": "mood", "y": "energy"}).json()
    assert pair["n"] == 1 and pair["r"] is None
    assert pair["points"][0]["x"] == 4
    assert client.get("/api/correlations/pair", params={"x": "a", "y": "b"}).status_code == 422
