from datetime import date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

# --- Ingest (bridge app -> API) ----------------------------------------------------------------


class IngestRecord(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="Health Connect record id")
    type: str = Field(
        pattern=r"^[a-z_]{1,40}$", description="sleep, steps, heart_rate, exercise, ..."
    )
    source: str = Field("", max_length=200, description="Package of the app that wrote it")
    start: AwareDatetime
    # Instant records (weight, resting heart rate) have no end.
    end: AwareDatetime | None = None
    last_modified: AwareDatetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Snapshot(BaseModel):
    """Every record of one type that Health Connect has from `since` on. Records of that type in
    Compass that start in this range and are not listed are gone from Health Connect."""

    type: str = Field(pattern=r"^[a-z_]{1,40}$")
    since: AwareDatetime
    ids: list[str] = Field(default_factory=list, max_length=5000)


class IngestPayload(BaseModel):
    device: str | None = Field(None, max_length=120)
    app_version: str | None = Field(None, max_length=40)
    records: list[IngestRecord] = Field(default_factory=list, max_length=5000)
    deleted: list[str] = Field(default_factory=list, max_length=5000)
    snapshots: list[Snapshot] = Field(default_factory=list, max_length=20)


class IngestResult(BaseModel):
    received: int
    created: int
    updated: int
    unchanged: int
    deleted: int
    restored: int = Field(0, description="Deleted earlier, now back in Health Connect")
    invalid: int
    days: int = Field(description="Local days whose daily metrics were recomputed")


class IngestStatus(BaseModel):
    ok: bool
    last_success_at: datetime | None
    last_error: str | None


# --- Reading -----------------------------------------------------------------------------------


class SleepStageRead(BaseModel):
    start: datetime
    end: datetime
    stage: str


class SleepNightRead(BaseModel):
    id: int
    local_date: date
    start_at: datetime
    end_at: datetime
    in_bed_minutes: int
    asleep_minutes: int
    deep_minutes: int | None
    light_minutes: int | None
    rem_minutes: int | None
    awake_minutes: int | None
    source_app: str


class HeartRatePoint(BaseModel):
    time: datetime
    bpm: int


class SleepNightDetail(SleepNightRead):
    stages: list[SleepStageRead]
    heart_rate: list[HeartRatePoint] = Field(description="5-minute averages during the night")


class DailyMetricsRead(BaseModel):
    date: date
    steps: int | None
    kcal_burned: int | None
    resting_hr: int | None
    hr_min: int | None
    hr_avg: int | None
    hr_max: int | None
    sleep_minutes: int | None


class WorkoutRead(BaseModel):
    id: str
    source_app: str
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    title: str | None
    exercise: str | None
    gymday_duplicate: bool = Field(description="Same time as a Gym Day session")


class HealthAverages(BaseModel):
    sleep_minutes: int | None
    deep_minutes: int | None
    light_minutes: int | None
    rem_minutes: int | None
    awake_minutes: int | None
    resting_hr: int | None
    steps: int | None


class SyncStatus(BaseModel):
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    device: str | None


class DayHeartRateRead(BaseModel):
    date: date
    points: list[HeartRatePoint] = Field(description="5-minute averages over the local day")
    min: int | None
    max: int | None
    avg: int | None
    resting: int | None
    last: HeartRatePoint | None = Field(description="Newest single sample of the day")
    sleep_start: datetime | None = Field(description="The night that ended this day")
    sleep_end: datetime | None


class ExtraDayRead(BaseModel):
    """Values the watch app writes only on some devices; null when there is none."""

    date: date
    oxygen_saturation: float | None = Field(None, description="SpO2 in percent, day average")
    heart_rate_variability: float | None = Field(None, description="HRV (RMSSD) in ms")
    respiratory_rate: float | None = Field(None, description="Breaths per minute")
    distance: float | None = Field(None, description="Meters")
    active_calories: float | None = Field(None, description="kcal")


class HealthSummaryRead(BaseModel):
    since: date
    until: date
    last_night: SleepNightDetail | None
    nights: list[SleepNightRead]
    days: list[DailyMetricsRead]
    averages: HealthAverages
    workouts: list[WorkoutRead]
    extras: list[ExtraDayRead] = Field(default_factory=list)
    sync: SyncStatus | None
