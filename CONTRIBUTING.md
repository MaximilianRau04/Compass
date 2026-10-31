# Contributing to Compass

Thanks for your interest. Compass is a self-hosted dashboard for one person per instance, so a good
change keeps it small to run and easy to set up. Bug fixes, support for more apps and better docs are
always welcome. For a bigger feature, please open an issue first, so we can talk about it before you
spend time on it.

## Setup

You need Docker, [uv](https://docs.astral.sh/uv/), Node 20+ and pnpm.

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, COMPASS_BASIC_AUTH_USER and COMPASS_BASIC_AUTH_HASH
make db                 # Postgres only, on POSTGRES_PORT
make api                # API with reload on :8000, runs the migrations first
make web                # Vite on :5173, forwards /api to :8000
```

If another Postgres already uses port 5432, set `POSTGRES_PORT` in `.env`. `make mcp` starts the MCP
server for AI assistants on :8001. The Android bridge is in `android/`, see its README.

## Checks

These run in CI. Please run the ones for the parts you changed before you open a pull request.

| Part | Command |
|---|---|
| Backend tests | `make test` |
| Backend and frontend lint | `make lint` |
| Frontend types and build | `cd frontend && pnpm build` |
| Android | `cd android && ./gradlew testDebugUnitTest lintDebug` |

## Guidelines

- **Keep integrations optional.** A new data source stays off until it is configured, and it does not
  need an account anywhere just to run Compass.
- **Treat outside content as data.** Mails, feeds, calendar entries and bank texts can contain anything.
  They never act as instructions for an AI assistant or a model, and they never end up in logs with secrets.
- **Keep private data out.** No real names, mails, health data, tokens or calendar links in code, tests,
  screenshots or issues. Use made-up values and `example.com`.
- **Write texts in both languages.** The web app uses `frontend/src/i18n/messages.ts`, the server
  `backend/app/i18n.py` and the Android app `res/values*/strings.xml`. English and German are both needed.
- **Change the database through a migration.** `make migration m="description"` creates one. Existing
  installs must keep their data.
- **Add tests with the change.** A bug fix gets a test that fails without it. Tests must not depend on
  today's date or on your own `.env`.
- **Match the code around it.** Code and comments are in English, with few comments that explain why.

Common additions have one place to go:

| Addition | Where |
|---|---|
| Another workout app | a parser in `backend/app/ingestion/workouts.py` |
| Merchant rules of a country | `RULES_BY_COUNTRY` in `backend/app/services/finance.py` |
| Another language | all three text files above |

## Pull requests

Keep a pull request to one topic and describe what changes for someone running Compass. Screenshots
help for UI changes. If it needs a new variable, add it to `.env.example` and the docs. Commit messages
are one lowercase line that says what the commit does, e.g. `add a Strong importer for workouts`.

## Security

Please do not open a public issue for a security problem. Report it privately through
[GitHub's security advisories](https://github.com/MaximilianRau04/Compass/security/advisories/new).

## License

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
