# Compass on iOS (Apple Health)

Apple Health only lives on the iPhone, like Health Connect on Android, so something on the phone has
to send the data to Compass. There are two ways:

| | Compass Bridge (this folder) | Health Auto Export |
|---|---|---|
| What | own app, reads HealthKit | paid app from the App Store |
| Deletions in Apple Health | arrive in Compass | do not arrive |
| Sleep phases | always | only with "Summarize Data" off |
| Install | build with Xcode on a Mac | App Store |
| Status | **not yet tested on a real iPhone** | backend tested against the documented format |

Both send to the same server and the same token (`HEALTH_TOKEN`). Use one of them, not both at the
same time: each would bring its own copy of the same steps and nights (Compass takes the larger
source per day, so nothing adds up, but nights would show twice).

## Server

Set `HEALTH_TOKEN` in `.env` (`openssl rand -hex 32`) and redeploy. A server that still has
`HEALTHCONNECT_TOKEN` keeps working; both bridges and Health Auto Export use whichever is set. Check
from your computer:

```bash
curl -H "Authorization: Bearer <token>" https://<dashboard host>/api/ingest/health
```

It must answer `{"ok": true, ...}`. The phone reaches the server the same way as the dashboard, over
your VPN if the server is only reachable there.

## Option 1: Compass Bridge

A small SwiftUI app. It only reads Apple Health and only talks to your server.

- Reads sleep (with phases), steps, heart rate, resting heart rate, heart rate variability (SDNN),
  blood oxygen, breathing rate, walking and running distance, active and resting energy, weight,
  nutrition (energy, protein, carbohydrates, fat, saturated fat, fiber, sugar, sodium, potassium,
  calcium, iron) and workouts.
- Each type has its own HealthKit anchor (`HKAnchoredObjectQuery`). The first sync reads the last
  *N* days (setting in the app, default 30); after that only what was added or deleted since. An
  anchor moves on only after Compass accepted the batch; the import is idempotent.
- Sleep is one sample per phase in HealthKit. The app groups the phases of each source into nights
  (a new night after more than 2 hours without a phase) and sends the nights of the last 3 days
  with every sync, with a snapshot, so a changed or deleted night arrives as such. Time in bed that
  no phase covers counts as awake in bed.
- Active energy also counts towards the calories burned of the day, together with resting energy
  (Health Connect has one total instead).
- HealthKit measures heart rate variability as SDNN, Health Connect as RMSSD. They are not
  comparable, so Compass shows them as two values.
- Nutrition: HealthKit has no meals, only nutrients (apps like MyFitnessPal write one sample per
  food and nutrient). Compass shows the day as one meal.

### Build and install

Requirements: a Mac with Xcode 16 or newer, [XcodeGen](https://github.com/yonaskolb/XcodeGen)
(`brew install xcodegen`) and an Apple account.

```bash
cd ios
(cd Core && swift test)   # records, sleep grouping, contract test against the backend fixture
xcodegen generate         # CompassBridge.xcodeproj from project.yml
open CompassBridge.xcodeproj
```

In Xcode: target CompassBridge, Signing & Capabilities, choose your team. In a fork, change
`PRODUCT_BUNDLE_IDENTIFIER` in `project.yml` to an id of your own first. Connect the iPhone, turn on
Developer Mode on it (Settings, Privacy & Security), and run.

With a free Apple account the app has to be installed again every 7 days. TestFlight or a longer
signature needs the paid Apple Developer Program. CI only checks that the app builds (unsigned, for
the simulator) and runs the core tests.

### Setup on the phone

1. Server address (`https://<dashboard host>`, no `/api`) and the token, "Save and test".
2. "Grant access": allow all types. iOS never tells an app what was denied; those types just stay
   empty in Compass.
3. "Sync now" for the first run.

After that it syncs by itself: HealthKit wakes the app when new data is written (at most hourly),
plus an app refresh about every hour, and every time you open the app. iOS decides when background
work really runs, and Apple Health cannot be read while the phone is locked, so a sync can be late;
opening the app catches up. "Read again" reads the whole range again; Compass stores nothing twice.

The app follows the phone's language (English, German).

### Data contract

The records are the ones of the Android bridge (`android/README.md`, "Data contract"), with ids
prefixed `hk:`. `ios/Core` builds them without HealthKit; `ContractTests.swift` checks its output
against `backend/tests/fixtures/healthkit_records.json`, which the backend test suite ingests
(`test_healthkit_contract.py`). After changing the mapping on purpose, run
`UPDATE_CONTRACT=1 swift test` in `ios/Core` and then the backend tests.

### Open on a real device

The app was written without a Mac and has not run on an iPhone yet. To check there: background
delivery and the refresh task, the sleep phases of an Apple Watch night, what MyFitnessPal or
Cronometer write as nutrition, and the activity names of less common workouts.

## Option 2: Health Auto Export

[Health Auto Export](https://apps.apple.com/app/id1115567069) reads Apple Health and posts it to a
URL. Compass takes its JSON at `/api/ingest/health-auto-export`.

In the app, create two automations of type REST API, one with data type Health Metrics and one with
Workouts:

| Setting | Value |
|---|---|
| URL | `https://<dashboard host>/api/ingest/health-auto-export` |
| Headers | `Authorization` = `Bearer <HEALTH_TOKEN>` |
| Export Format | JSON |
| Export Version | 2 |
| Summarize Data | off (sleep phases and single readings) |
| Date Range | Since Last Sync |
| Batch Requests | on |

Health metrics: select the ones Compass uses: Step Count, Heart Rate, Resting Heart Rate, Heart Rate
Variability, Blood Oxygen Saturation, Respiratory Rate, Walking + Running Distance, Active Energy,
Resting Energy (basal energy burned), Weight (body mass), Sleep Analysis and the dietary values
(Dietary Energy, Protein, Carbohydrates, Total Fat, Saturated Fat, Fiber, Dietary Sugar, Sodium,
Potassium, Calcium, Iron). Anything else is ignored; the answer lists it under `unknown`.

For the first run, "Export Existing Data" sends older data once.

What to know:

- The export has no record ids. Compass makes one from metric, source and time (and the food for
  nutrition), so sending the same data again stores nothing twice.
- Health Auto Export cannot report deletions: a reading deleted in Apple Health stays in Compass.
- With "Summarize Data" on, a night is only a total from falling asleep to waking up, without
  phases, and the hypnogram stays empty.
- The format is the one documented at help.healthyapps.dev (version 2). If a new version of the app
  changes it, readings it cannot place are counted under `skipped` in the answer.
