# Code- und UI-Review Compass

Stand: 8. November 2026, Commit `cc28fa9` plus die offene Änderung am Wochenreview auf der Heute-Seite.
Ziel: sauberer Code, klare Struktur, konsistente UI. Keine neuen Features.

## Kurzfazit

Compass ist in einem guten Zustand. Alle automatischen Checks sind grün, die Schichten sind sauber
getrennt und die Sicherheit ist durchdacht. Die wichtigsten Punkte betreffen die UI am Handy: Die
Heute-Seite läuft horizontal über, die Checkbox einer Aufgabe ist nur 20 px groß, und im hellen Modus
erreichen drei Farbkombinationen den AA-Kontrast nicht. Im Code sind es vor allem die große Datei
`mcp/server.py`, ein Button-Helfer, den nicht alle Stellen nutzen, und einige Lücken in `.env.example`.

## Stand der Umsetzung (Phase 2)

| Punkt | Stand | Was geändert wurde |
|---|---|---|
| K1 Überlauf Heute | erledigt | Grid am Handy `grid-cols-[minmax(0,1fr)]`; dasselbe Muster bei den Vorlagen im Workout-Logger. Gemessen: 433 → 390 px |
| K2 Abhak-Kreis | erledigt | unsichtbares `::before`, Trefferfläche gemessen 42 × 38 px, Optik unverändert |
| W1 `.env.example` | erledigt | `LOG_LEVEL`, `ILIAS_DEADLINE_SUFFIXES`, `MCP_ACCESS_TOKEN_TTL`, `MCP_REFRESH_TOKEN_TTL`, `MCP_WRITE_LIMIT_PER_HOUR` |
| W2 Compose-Port | erledigt | Standard `127.0.0.1:8080`, geprüft mit `docker compose config` |
| W3 `mcp/server.py` | erledigt | aufgeteilt in `core`, `schemas`, `guards`, `prompts` und `tools/*` (10 Module); neuer Vertragstest `tests/test_mcp_contract.py` mit Fixture; alle 123 Definitionen per AST als unverändert geprüft |
| W4 Buttons | erledigt | 16 Buttons auf `button()` (der 17. Fund in `Mail.tsx` war ein Badge, kein Button) |
| W5 Kontrast | erledigt | hell: `--brass` `#906623`, `--signal` `#ce2f36`; die MCP-Login-Seite zieht mit |
| W6 Touch-Ziele | erledigt | Themen-× im Interessenprofil (das waren die 19 × 20 px, nicht die Daumen), Daumen, Kategorie-Select am Handy, Budget-Buttons, „Als Tabelle“ |
| N3 Wiederholtes Markup | erledigt | `pageTitle` und `overlay` in `lib/ui.ts` (12 Titel, 6 Overlays) |
| N8 `strict` | erledigt | ausdrücklich in beiden tsconfigs |
| N1, N2, N4–N7, N9–N15 | offen | siehe „Bewusst offen“ am Ende |

Nach jedem Schritt liefen ruff, oxlint, `tsc -b`, `pnpm build` und `pytest`, am Ende alles grün
(319 Tests, einer davon neu). Die UI-Schritte wurden mit Screenshots in 390 px und 1440 px
geprüft: kein Überlauf, keine Konsolenmeldungen.

### Was geprüft wurde

| Check | Ergebnis |
|---|---|
| `ruff check`, `ruff format --check` | grün, 145 Dateien |
| `oxlint`, `tsc -b` (TS 6.0, `strict` ist dort Standard) | grün, 0 Fehler, kein `any`, kein `@ts-ignore` |
| `pytest` | 318 bestanden in 7 s; Abdeckung fast überall über 60 %, Ausnahmen `worker.py` (0 %) und `enablebanking.py` (51 %) |
| `pnpm audit --prod`, `pip-audit` | keine bekannten Schwachstellen |
| Git-Historie auf Secrets | nichts gefunden; `.env`, `*.private.md`, `data/` wurden nie committet |
| Import-Zyklen im Backend (AST) | keine; `services` importiert nie aus `api` oder `mcp` |
| Frontend-Typen gegen OpenAPI | keine Abweichung zwischen `api/types.ts` und den Pydantic-Schemas |
| i18n DE/EN | vollständig; im Frontend per Typ erzwungen, im Backend gleiche Schlüssel |
| TODO, auskommentierter Code, `console.log`, verwaiste Dateien | keine |
| UI | 12 Seiten in 390 px hell, 390 px dunkel und 1440 px hell (Demo-Datenbank), Konsole mitgeschnitten, Überlauf, Touch-Ziele, Labels und Kontraste gemessen |
| Browser-Konsole | auf keiner Seite Fehler oder Warnungen |

### Was schon gut ist (bitte so lassen)

- Die Auth-Kette ist klar: Basic Auth in Caddy für alles außer `/api/health` und `/api/ingest/*`,
  die Ingest-Endpunkte prüfen eigene Bearer-Tokens mit `hmac.compare_digest` *vor* dem Lesen des
  Bodys. Dazu CSRF-Schutz über `Sec-Fetch-Site`, CSP, `frame-ancestors 'none'` und `nosniff`.
- Der MCP-Server hat eigenes OAuth 2.1 mit PKCE, bcrypt-Login, Throttling pro IP und global,
  Audit-Log und Schreiblimit pro Stunde. Die Tools haben `Field`-Grenzen und Read/Write-Annotationen.
- Breite `except Exception` gibt es nur an begründeten Stellen (Worker am Leben halten, kaputtes
  MIME), jeweils mit Kommentar.
- Farben sind vollständig als Tokens angelegt (`index.css`), in keiner Komponente steht ein Hex-Wert.
  Der Dark Mode hat überall ausreichend Kontrast. `:focus-visible` ist global gesetzt, und
  `prefers-reduced-motion` wird beachtet.
- Uploads und Feeds haben Größenlimits (`MAX_BYTES`), der Kalender-Zeitraum ist begrenzt.

---

## Kritisch

### K1 · UI: Die Heute-Seite läuft am Handy horizontal über
`frontend/src/pages/Today.tsx:220`

Das Layout-Grid hat nur ab `lg:` eine Spalte `minmax(0,1fr)`. Am Handy gilt die implizite
`auto`-Spalte, und deren Mindestbreite ist der breiteste Inhalt. Die Mail-Vorschauen nutzen
`truncate` (kein Umbruch), deshalb ziehen sie die ganze Spalte auf die Länge des Textes. Gemessen
bei 390 px: Seitenbreite 433 px. Die Kacheln, das Wochenreview und die Mails ragen rechts aus dem
Bild, und die Seite lässt sich seitlich verschieben. Mit echten Mails passiert das fast immer.

**Vorschlag:** auch am Handy eine Spalte `grid-cols-[minmax(0,1fr)]` setzen (oder `min-w-0` an die
Kinder des Grids). Das ist eine einzeilige Änderung.

### K2 · UI: Die Checkbox einer Aufgabe ist nur 20 × 20 px groß
`frontend/src/components/TaskItem.tsx:55`

Aufgaben abhaken ist die häufigste Aktion am Handy. Der Kreis ist `h-5 w-5` ohne größere
Trefferfläche, das liegt unter dem WCAG-Minimum von 24 px und weit unter den üblichen 44 px. Er
kommt auf Heute und Aufgaben je Zeile vor.

**Vorschlag:** Die Optik bleibt, aber der Button wird größer (z. B. `p-3 -m-3` oder ein
Pseudo-Element mit `before:absolute before:-inset-3`).

---

## Wichtig

### Sicherheit und Konfiguration

**W1 · In `.env.example` fehlen fünf Optionen**
`backend/app/config.py:58, 66–68, 87`: `LOG_LEVEL`, `MCP_ACCESS_TOKEN_TTL`, `MCP_REFRESH_TOKEN_TTL`,
`MCP_WRITE_LIMIT_PER_HOUR` und `ILIAS_DEADLINE_SUFFIXES` kann man setzen, sie stehen aber nirgends.
**Vorschlag:** mit Standardwert und einer Zeile Erklärung ergänzen.

**W2 · Die Standard-Ports in Compose sind uneinheitlich**
`infra/docker-compose.yml:72`: `${COMPASS_HTTP_PORT:-8080}` bindet auf alle Interfaces, wenn die
Variable fehlt. Der MCP-Port daneben ist dagegen standardmäßig `127.0.0.1:8081`. `make setup` und
`.env.example` setzen zwar `127.0.0.1:8080`, aber eine handgeschriebene `.env` ohne die Zeile
stellt das Dashboard per HTTP ins Netz (nur mit Basic Auth geschützt).
**Vorschlag:** den Standard auf `127.0.0.1:8080` setzen. Das ändert nichts für dich.

### Struktur

**W3 · `backend/app/mcp/server.py` hat 1905 Zeilen**
Die Datei enthält 38 Tools, 5 Prompts, über 50 Output-Modelle und die Guards. Die Modelle stehen
teilweise mitten zwischen den Tools (`FinanceMonthOut` in Zeile 1218, `NotificationOut` in 1398,
`DayRowOut` in 1646).
**Vorschlag:** ein Paket `app/mcp/` mit `schemas.py` (alle Output-Modelle), `guards.py`
(`_audited`, `_caller`, Schreiblimit) und `tools/` nach Bereich (tasks, calendar, health,
nutrition, mail, news, notes, finance, review), dazu `prompts.py`. `server.py` erstellt nur noch
`mcp` und importiert die Module. **Toolnamen, Parameter und Rückgaben bleiben gleich.** Ein Test
vergleicht die Tool-Liste und die JSON-Schemas vorher und nachher (siehe Phase 2).

**W4 · Der Button-Helfer wird an 17 Stellen umgangen**
`frontend/src/lib/ui.ts` definiert `button(kind, size)` mit vier Arten. Trotzdem sind Buttons an
17 Stellen von Hand gestylt, mit acht Varianten für primär (unterschiedliches Padding,
`disabled:opacity-30/40/50`, mal mit `hover:opacity-90`, mal mit `brightness`). Betroffen sind
`BodyPanel.tsx:51`, `QuickAdd.tsx:121`, `NoteSheet.tsx:182`, `Training.tsx:355`,
`News.tsx:178, 231`, `Settings.tsx:53`, `Share.tsx:61, 93`, `Nutrition.tsx:49, 236`,
`Notes.tsx:81`, `Welcome.tsx:86, 151`, `Mail.tsx:46` und `Finance.tsx:303, 422`.
**Vorschlag:** alle auf `button()` umstellen. Der kleine Anlegen-Button in Quick Add bleibt
eventuell eine bewusste Ausnahme (siehe offene Fragen).

### UI und Barrierefreiheit

**W5 · Im hellen Modus erreichen drei Kombinationen den Kontrast nicht** (`frontend/src/index.css`)

| Kombination | Kontrast | Wo |
|---|---|---|
| `--brass-ink` (weiß) auf `--brass` | 3,6 : 1 | alle Primär-Buttons |
| `--brass` auf `--paper` | 3,2 : 1 | Outline-Buttons in Brass, aktive Links |
| `--signal` auf `--paper` | 4,4 : 1 | „fällig vor …“ in 11 px |

AA verlangt 4,5 : 1 für normalen Text. Im Dark Mode passen alle drei (7,0 / 7,5 / 5,9).
**Vorschlag:** `--brass` im hellen Modus etwas dunkler (etwa `#94681f`) und `--signal` etwa
`#c02a31`. Das ist nur eine Token-Änderung, der Charakter der Palette bleibt. Vorher und nachher
gibt es Screenshots zum Vergleich.

**W6 · Weitere zu kleine Touch-Ziele am Handy**
- Die News-Daumen sind 19 × 20 px (`frontend/src/pages/News.tsx:25`).
- Die Kategorie-Selects in Finanzen sind 23 px hoch (`frontend/src/pages/Finance.tsx:356`),
  das betrifft jede Umsatzzeile.
- „Als Tabelle“ unter den Diagrammen ist 16 px hoch (`frontend/src/components/DataBlocks.tsx:19`).
- „Budget setzen“ in Finanzen ist 16 px hoch.

**Vorschlag:** wie bei K2 die Trefferfläche vergrößern, ohne die Optik zu ändern (`py-2 -my-2`).

---

## Nice-to-have

### Code

- **N1 · Lange Funktionen:** `parse_quick_add` (148 Zeilen, `services/quick_add.py:161`) und
  `healthconnect.ingest` (115 Zeilen, `ingestion/healthconnect.py:121`) ließen sich in benannte
  Schritte zerlegen. Beide sind gut getestet. Das Risiko ist klein, der Nutzen aber auch: Sie lesen
  sich als lineare Abfolge.
- **N2 · Große Frontend-Dateien:** `WorkoutLog.tsx` (783 Zeilen, `Active` allein 140) und
  `charts.tsx` (647 Zeilen, vier Diagrammtypen). Vorschlag: `pages/workout/` mit Start, Active und
  ExerciseCard, und je ein Diagramm pro Datei unter `components/charts/`.
- **N3 · Wiederholtes Markup:** Die Seitenüberschrift `font-display text-5xl … sm:text-6xl` steht
  12-mal wortgleich, das Dialog-Overlay 6-mal. Vorschlag: `<PageTitle>` und `<SheetOverlay>`.
- **N4 · Schriftgrößen als Einzelwerte:** 166-mal `text-[10px]` bis `text-[15px]`, am häufigsten
  `text-[11px]` (99-mal). Vorschlag: Tokens `--text-2xs` (11 px) und `--text-3xs` (10 px) in
  `@theme`. Wiederholte Kombinationen wie `font-mono text-[11px] text-muted` (über 30-mal) werden
  dann zu einer Utility oder einer kleinen `<Meta>`-Komponente.
- **N5 · Direkte DB-Abfragen in 4 API-Modulen** (`api/areas.py`, `api/news.py`,
  `api/nutrition.py`, `api/training.py`, je eine). Das könnte in den Service, ist aber kein Problem.
- **N6 · Tags und Notizen:** Das Modell sagt `ARRAY(String(60))`, gespeichert wird aber auch ein Tag
  mit 61 Zeichen (getestet), und `notes` hat in API und MCP kein Längenlimit. Vorschlag: `max_length`
  in `TaskCreate` und `TaskUpdate`. **Das ändert die API leicht** (zu lange Eingaben ergeben dann
  422), deshalb nur nach deinem OK.
- **N7 · `revoke_all_tokens`** wird nur über einen `python -c`-Einzeiler in `docs/deploy.md:333`
  aufgerufen. Vorschlag: ein Unterbefehl `python -m app.cli revoke-mcp-tokens` neben `rebuild-health`.
- **N8 · `tsconfig.app.json`:** `strict` gilt nur, weil TypeScript 6 es standardmäßig einschaltet.
  Vorschlag: `"strict": true` ausdrücklich setzen, damit ein Downgrade oder ein Editor mit älterem
  TS nicht still lockerer prüft.
- **N9 · `mcp_public_url`** hat im Code den Standard `http://localhost:8001`
  (`config.py:65`), in `.env.example` steht `http://localhost:8081`. Beides funktioniert (`make mcp`
  gegenüber Docker), ein Kommentar würde aber helfen.

### Sicherheit (Defense in depth)

- **N10 · Client-IP beim MCP-Login:** `--forwarded-allow-ips=*` (`infra/docker-compose.yml:48`)
  bewirkt, dass uvicorn den *linken* Eintrag von `X-Forwarded-For` nimmt. Caddy vertraut privaten
  Netzen und hängt an. Das Throttling pro IP und `COMPASS_MCP_ALLOWED_IPS` stimmen deshalb nur,
  weil der Host-Proxy den Header überschreibt. Bei dir ist das so (`docs/deploy.private.md:99`) und
  in `docs/deploy.md:26` als Voraussetzung dokumentiert. Robuster wäre
  `header_up X-Forwarded-For {client_ip}` im MCP-Block des Caddyfiles, dann hängt nichts mehr am
  Proxy davor.
- **N11 · Body-Größe vor der Token-Prüfung:** `POST /api/ingest/mail/triage`
  (`api/ingest.py:109`) hat einen Pydantic-Body. FastAPI liest ihn vollständig, *bevor* die
  Token-Dependency läuft, und der Dashboard-Block im Caddyfile hat kein `request_body`-Limit. Der
  Endpunkt ist nur im VPN erreichbar, das Risiko ist also klein. Vorschlag:
  `request_body { max_size 25MB }` für `/api/*` (die größte legitime Anfrage ist der
  Health-Connect-Batch mit 20 MB).

### UI

- **N12 · Kein Ladezustand in Aufgaben und Kalender:** Ohne Cache bleibt die Liste kurz leer, bevor
  die Daten da sind (`pages/Tasks.tsx:123`, `pages/Calendar.tsx:165`). Durch den localStorage-Cache
  fällt das selten auf. Vorschlag: dieselbe Zeile `common.loading` wie auf den anderen Seiten.
- **N13 · Finanzen am Handy:** Alle Umsätze der letzten 90 Tage stehen untereinander, im Demo sind
  das rund 6400 px Seitenhöhe. Ein „mehr anzeigen“ wie in den News (`News.tsx:344`) wäre
  konsistent, wäre aber eine kleine Verhaltensänderung (siehe offene Fragen).

### Tests und Repo

- **N14 · `worker.py` ist ungetestet (0 %).** Die Jobs selbst sind getestet, nur die Verdrahtung
  nicht. Vorschlag: ein Smoke-Test, dass alle Jobs registriert sind und mit leerer Datenbank ohne
  Fehler durchlaufen.
- **N15 · `.github/modernize/`** ist nicht getrackt, sondern liegt nur lokal als Rest eines
  Java-Upgrade-Tools. Das kannst du löschen.

---

## Offene Fragen (Absicht oder Fehler?)

1. **Sprachumschalter DE/EN oben auf jeder Seite am Handy:** Er nimmt die erste Zeile ein. Ist das
   gewollt, oder darf er am Handy in „Mehr“ oder in die Einstellungen?
2. **Quick-Add-Button „ANLEGEN“** in Versalien und kleiner als die anderen Primär-Buttons: bewusst so
   gestaltet, oder soll er auf `button('primary')`?
3. **N6 (Längenlimits) und N13 (Finanzliste kürzen)** ändern das Verhalten leicht. Sollen sie in
   Phase 2 mit rein?
4. **Commits:** Du committest in Compass selbst. Soll ich in Phase 2 die Änderungen pro Thema
   vorbereiten und dir jeweils eine Commit-Nachricht vorschlagen, statt selbst zu committen?

## Bewusst offen

Ohne Antwort auf die offenen Fragen habe ich die vorsichtige Variante gewählt:

- **Sprachumschalter und Quick-Add-Button** bleiben wie sie sind (Fragen 1 und 2).
- **N6 Längenlimits und N13 Finanzliste kürzen** ändern Verhalten, deshalb nicht umgesetzt (Frage 3).
- **N1 lange Backend-Funktionen und N2 große Frontend-Dateien:** Das Aufteilen bringt wenig Lesbarkeit
  und kostet Risiko in getesteter Kernlogik (Quick Add, Health-Connect-Import). Es lohnt sich erst,
  wenn dort ohnehin etwas geändert wird.
- **N4 Schrift-Tokens:** betrifft 166 Stellen in fast jeder Datei. Das wäre ein eigener, rein
  mechanischer Umbau, den ich nicht zusammen mit den sichtbaren UI-Fixes machen wollte.
- **N7 CLI-Befehl für `revoke_all_tokens`:** wäre ein neuer Befehl, also ein kleines Feature.
- **N10, N11 Proxy-Header und Body-Limit:** ändern das Caddyfile im Betrieb. In deinem Setup ist beides
  abgesichert; besser zusammen mit einem Deploy, bei dem du danach testest.
- **N5, N9, N12, N14, N15:** klein und ohne Eile; N15 ist nur ein lokales Verzeichnis.

## Plan für Phase 2 (nach deinem OK)

Reihenfolge nach Nutzen und Risiko. Jeder Schritt ist ein eigener Commit, und nach jedem laufen
`ruff`, `oxlint`, `tsc -b`, `pnpm build` und `pytest`. Nach UI-Schritten kommen Screenshots in
390 px und 1440 px.

1. `fix(ui)`: Überlauf auf der Heute-Seite (K1)
2. `fix(ui)`: größere Touch-Ziele (K2, W6)
3. `fix(ui)`: Kontrast-Tokens im hellen Modus (W5)
4. `refactor(ui)`: Buttons auf `button()` umstellen (W4), dazu `PageTitle` und `SheetOverlay` (N3)
5. `chore(config)`: `.env.example` vervollständigen, Compose-Standardport, `strict` explizit (W1, W2, N8)
6. `refactor(mcp)`: `server.py` aufteilen (W3). Vorher kommt ein Test, der Tool-Namen und
   Input-/Output-Schemas als Snapshot festhält, damit die Claude-Anbindung garantiert gleich bleibt.
7. Optional, je nach deinen Antworten: N1, N2, N4, N7, N10–N14
