# Compass

Personal productivity and life dashboard: tasks, deadlines, training, sleep, nutrition,
mail, news and notes, with its own MCP server for Claude.

## Quick add

Tasks can be captured in one line. German and English keywords both work:

```
morgen 14 Uhr Blatt 3 abgeben #uni !hoch
tomorrow 2pm hand in sheet 3 #uni !high
Bericht schreiben @montag bis 30.10. #arbeit
Müll rausbringen jeden Montag #privat
```

| Syntax | Meaning |
|---|---|
| `heute`/`today`, `morgen`/`tomorrow`, `freitag`/`friday`, `nächste woche`/`next week`, `in 3 tagen`/`in 3 days`, `12.11.`, `12. november`, `nov 12` | due date (deadline), optionally after `bis`/`am`/`by`/`on`/`due` |
| `@morgen`, `@friday`, … | planned day instead of the deadline |
| `14 Uhr`, `14:30`, `um 9`, `2pm`, `at 9` | due time (today if no date is given) |
| `#uni` | area if it exists, otherwise a tag |
| `!`, `!!`, `!!!`, `!hoch`/`!high`, `!dringend`/`!urgent`, `!niedrig`/`!low` | priority |
| `täglich`/`daily`, `werktags`/`weekdays`, `jeden Montag`/`every monday`, `alle 2 wochen`/`every 2 weeks`, `monatlich`/`monthly` | recurrence |

The interface is available in German and English (switch in the navigation). On Android, links and text can be shared into Compass from any app once the PWA is installed.

## Structure

| Directory | Contents |
|---|---|
| `backend/` | FastAPI API, worker (APScheduler) and MCP server for Claude. Python 3.12, uv, SQLAlchemy 2, Alembic |
| `frontend/` | React + TypeScript + Vite, served from the Caddy image |
| `android/` | Health Connect bridge app (Kotlin), pushes sleep and health data to the API |
| `infra/` | Docker Compose, Caddyfile |
| `data/` | Local raw data exports, not committed |

## Setup

```bash
cp .env.example .env    # fill in values, at least POSTGRES_PASSWORD
make up                 # build and start everything in Docker
```

The app is then available at http://localhost:8080, the API docs at http://localhost:8080/api/docs.

## Development

```bash
make db      # Postgres only, exposed on localhost
make api     # API with reload on :8000 (runs migrations first)
make web     # Vite dev server on :5173, proxies /api to :8000
make mcp     # MCP server with reload on :8001
make test    # backend tests
make lint    # ruff + oxlint
make migration m="description"   # new Alembic migration
```

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 20+ and pnpm.

## Calendars and ILIAS deadlines

The worker fetches ICS calendars every 30 minutes (`ILIAS_ICS_URL`, `CALENDAR_ICS_FEEDS` in `.env`)
and mirrors their events for the Today page and the calendar view of the Tasks tab. Entries of the
ILIAS feed that end in "(Abgabetermin)" become tasks with `source=ilias` instead: a sync never
duplicates them, only changes title and deadline (area, priority, planned day and status stay yours),
and cancels a deadline that disappears instead of deleting it.

## Training

The Training tab imports the Gym Day strength export (`daily_strength.csv`), either uploaded there or
shared from the phone (the installed PWA is a share target for CSV files). Importing the same or an
overlapping export again changes nothing. It shows volume per week, the push/pull/legs split and the
progression per exercise (estimated 1RM, top weight, reps). Exercises renamed in Gym Day can be merged
so their progression continues in one line.

## Sleep and health

Sleep, steps, heart rate and workouts come from the watch (Zepp) through Health Connect. Health Connect
only lives on the phone, so a small Android app (`android/`, see its README) pushes the changes every
hour to `/api/ingest/healthconnect`, protected by its own token (`HEALTHCONNECT_TOKEN`) instead of the
dashboard login. Every record is stored as it arrived; derived from it are sleep sessions with stages
(a night counts for the day of waking up), heart rate samples and daily metrics. When two apps write the
same steps or sleep, a day takes the source with the larger total instead of adding them up.

The Sleep tab shows last night with its stages, sleep per night, resting heart rate, steps and workouts
from other apps than Gym Day. Gym Day writes its sessions (without sets) to Health Connect as well;
Compass matches them with the sessions from the CSV export to fill in the duration in the Training tab.
A session that is only in Health Connect (no export, e.g. without Gym Day Premium) still shows up there,
with name, duration and split but without sets; a later export with its sets takes its place.
Nutrition and weight from Health Connect feed the Nutrition tab (below).

## Nutrition

MyFitnessPal writes every meal to Health Connect, so meals arrive with the bridge app like sleep does.
Compass sums them per day and meal (breakfast, lunch, dinner, snacks). If two apps write nutrition for
the same day, the one with more calories counts instead of both. The MFP data export (the zip MFP
mails, or its CSV files) fills in the past: upload it in the Nutrition tab or share it from the phone.
Importing it again changes nothing, and for days that also have Health Connect data, those win. Days
without entries were not logged and stay empty in the charts, never 0 kcal. The export's weight file
fills the weight history; new weights come from Health Connect.

Daily goals for calories and protein apply from the day they are set, so earlier days keep the goal
they had. The Nutrition tab shows today against the goals, calories and protein per day, average
macros and the full weight history.

## MCP server

Claude connects to Compass through its own MCP server (`app/mcp`), protected by OAuth with a
built-in login. Tools: `get_today`, `list_tasks`, `get_deadlines`, `get_task`, `list_areas`,
`get_calendar`, `training_summary`, `exercise_progress`, `sleep_summary`, `nutrition_summary`, `set_nutrition_goal`, `add_task`, `quick_add`, `update_task`,
`complete_task`; prompts: `daily_brief`, `weekly_review`.
There is no delete tool, cancelling a task is the undo, and every write is recorded in an audit log.

## Deployment

See [docs/deploy.md](docs/deploy.md): server setup behind a reverse proxy and a VPN, login, MCP and backups.
