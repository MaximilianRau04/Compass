# Compass Bridge (Android)

Small app that reads Health Connect on the phone and pushes it to Compass
(`POST /api/ingest/healthconnect`). Health Connect has no cloud API, so the server cannot fetch the
data itself.

- Reads sleep (with stages), steps, heart rate, resting heart rate, exercise sessions, nutrition,
  weight and total calories burned. It never writes to Health Connect.
- First run: creates a changes token, then reads the last *N* days (setting in the app, default 30).
  After that, an hourly WorkManager job only sends what changed since the last run, including
  deletions. The token only moves on after Compass accepted a batch; the import is idempotent, so a
  broken-off run just resends a few records.
- If the changes token expires (30 days without a sync) or other permissions are granted, the app
  reads the window again. "Read again" in the app does the same by hand.

## Build and install

Requirements: JDK 17+, Android SDK (platform 37). `local.properties` points Gradle at the SDK
(`sdk.dir=/home/<you>/Android/Sdk`), Android Studio writes it automatically.

```bash
cd android
./gradlew testDebugUnitTest      # JSON mapping test, also writes app/build/contract/records.json
./gradlew assembleRelease        # app/build/outputs/apk/release/app-release.apk
adb install -r app/build/outputs/apk/release/app-release.apk
```

In a fork, change `applicationId` in `app/build.gradle.kts` to a package name of your
own. A different id installs as a separate app.

The release APK is signed with the debug key of the machine that builds it. Android only installs an
update over an existing install when the key is the same, so always build on the same machine (or copy
`~/.android/debug.keystore`). CI builds and tests the app but does not publish an APK for that reason.

## Setup on the phone

1. On the server, set `HEALTHCONNECT_TOKEN` in `.env` (`openssl rand -hex 32`) and redeploy.
2. Your VPN must be connected on the phone if the server is only reachable there; the app talks to the
   dashboard address.
3. In the app: server address (`https://<dashboard host>`, no `/api`), the token, "Save and test".
4. "Grant permissions": allow all data types, reading in the background and older data.
5. Battery: switch off battery optimisation (button in the app). On Samsung also make sure the app is
   not under "Sleeping apps" or "Deep sleeping apps" in the battery settings.
6. "Sync now" for the first run. The hourly job starts by itself.

The app follows the phone's language (English, German).

The Sleep tab in Compass shows the last sync and its device; the app shows its own last result or error.

## Data contract

`HealthTypes.toJson` maps each record to `{id, type, source, start, end?, last_modified, data}`, with
times as UTC ISO strings. The unit test writes the JSON for every type to
`app/build/contract/records.json`; a copy lives in `backend/tests/fixtures/healthconnect_records.json`
and the backend test suite ingests it. After changing the mapping, copy the new file over and run the
backend tests.

## Open on the real device

Background reads depend on the Health Connect version (`FEATURE_READ_HEALTH_DATA_IN_BACKGROUND`); the
app shows whether the phone supports it. Without it, syncs only work while the app is open.
