# Current release: React frontend + local Ollama

The cumulative workspace now includes the primary React web app in `frontend/`, optional local Ollama in dev/test, and migration 006 for login row-lock privileges. Start with **[how-to-run.md](how-to-run.md)** for current startup and upgrade commands. The default dev web URL is http://127.0.0.1:3000 and API port is 8010. Streamlit is optional with the `legacy-ui` Compose profile.

Current verification: 169 Python tests and 6 React tests passed; 47 database tests skipped. React TypeScript/build passed. Live Docker/PostgreSQL/Ollama and browser/a11y checks remain outstanding. Phase 6 remains unfinished. See `docs/react-verification.md` and ADRs 028–030.

The remaining sections below are historical phase notes and may describe the earlier temporary interface. Use the current run guide for commands.

---

# Clinic Financial Intelligence — Phase 5 (cumulative)

Implementation through the analytics phase of Edgar J. Suárez Colón's SRD v1.0.
**105 local tests pass. 28 PostgreSQL integration tests remain unexecuted here.**
Docker startup also requires verification on a Docker-capable machine. No real
clinic data or stakeholder business assumptions have been used.

## One workspace; final product direction

This package includes Phases 1–3 together: one application, one database migration
history, one test suite and one Git history. No separate phase applications are
created. The final product will be a custom web app using the same FastAPI and
PostgreSQL backend; Streamlit is the temporary demo interface.

## Phase 3 analytics

The sidebar now switches between **Analytics** and **Imports**. The dashboard
includes weekly/monthly results, margins, growth, 4/12-week averages, fixed/variable
costs, expense category history, volatility and a separately protected provider
panel. All financial calculations live behind the API in pure Decimal functions.

Access defaults to disabled in `config/analytics.json`. General dashboard users
and users who can see provider costs must be explicitly listed separately. Only
approved public category labels are returned by the general API. Fully loaded
provider cost must be confirmed for the selected dates; otherwise contribution
shows as unavailable. No salary, benefits or overhead allocation is guessed.

### Enable a synthetic analytics demo

After generating the Phase 2 synthetic ingestion configuration below, run:

```sh
docker compose run --rm --user "$(id -u):$(id -g)" -v "$PWD/config:/config" migrate python -m app.analytics.demo --source /config/ingestion.demo.json --output /config/analytics.demo.json
cp config/analytics.demo.json config/analytics.json
docker compose restart api
```

This grants demo analytics/provider access only to the accounts already listed in
the explicitly synthetic ingestion setup. It does not confirm full provider costs.
Keep generated/copied runtime configuration local and out of commits.

For a clean worked example, use a fresh disposable demo database, open **Imports**,
and upload `examples/synthetic-analytics.csv` instead of the earlier three-row
sample. Select January 5 through February 15, 2026 in **Analytics**. Expected
revenue is **2,100.00**, expense **580.00**, net **1,520.00**, and the last 4-week
revenue average is **450.00**. The sample's expenses are all variable; zero fixed
cost reflects this synthetic input, not an assumption about a real practice.
If both example files are imported, their totals combine; the examples are not
alternative versions of one dataset. Provider contribution remains unavailable
until the underlying fully loaded cost is explicitly confirmed.

See `docs/analytics-api.md` for response contracts and configuration semantics.

## Included

- Phase 1: authenticated FastAPI, revocable sessions, PostgreSQL star schema,
  forward-only migrations, structured application logs and separate audit records.
- Pluggable CSV, XLSX and structured-PDF extraction with explicit mappings.
- Per-row validation and specific rejection reasons, without rejected cell values.
- Durable PostgreSQL ingestion jobs and a separate worker container.
- Content-hash uniqueness, transaction-level atomicity, safe failed-job retry,
  and a unique source-upload/source-row constraint as an additional safeguard.
- Streamlit sign-in, upload, progress, row counts and rejection details.
- Operator-configured ingestion, analytics and separate provider access; disabled by default.
- Phase 3 pure financial analytics, read views, exact JSON contracts and dashboard.

Simulations, text-to-SQL, the final custom frontend and Phase 6 hardening remain
outstanding. Streamlit is the temporary local test/demo UI, not the final product
frontend. Read `docs/phase-3-report.md` and `docs/product-architecture.md`.

## Start locally

Requires Docker Engine with Compose v2. Run from this directory.

1. Copy `.env.example` to `.env` and supply four independent URL-safe secrets.
   Generate each with `python -c "import secrets; print(secrets.token_hex(32))"`.
   Do not commit `.env`. Use hexadecimal secrets because Compose embeds them
   in database connection URLs.
2. Run `docker compose up --build -d`.
3. Create a login with
   `docker compose run --rm migrate python -m app.bootstrap your-username`.
   The terminal asks for the password twice. No default account exists.
4. Open `http://127.0.0.1:8501` for the temporary analytics/import demo UI.
   The API listens at `http://127.0.0.1:8000`.

The default `config/ingestion.json` disables imports. It does not assume the clinic's
export, currency, accounting conventions, patient-identifier scope or users.
Use the explicit synthetic demo below to exercise the workflow on a disposable DB.
Do not expose this local HTTP setup publicly or connect real clinic data before
required hardening and onboarding are complete.

### Existing Phase 1 installation

Preserve the existing database volume and `.env`. Rebuild the services with
`docker compose up --build -d`; the migration runner applies missing `002_ingestion.sql` through `005_natural_language_queries.sql` in order.
Migration 001 remains byte-identical. No role or password rotation is required
for this phase. Never remove a real database volume to perform an upgrade.

## Synthetic demonstration

Use an empty disposable database only. The example numbers, dates, category and
provider identifiers are synthetic test fixtures, not clinic defaults.

1. Create a synthetic login with the bootstrap command above.
2. Generate the demo dimensions and configuration (POSIX shell):

```sh
docker compose run --rm --user "$(id -u):$(id -g)" -v "$PWD/config:/config" migrate python -m app.ingestion.demo your-username --output /config/ingestion.demo.json --confirm-disposable
cp config/ingestion.demo.json config/ingestion.json
docker compose restart api
```

The generator refuses a nonempty transaction table and an existing output path.
The account must already exist. The output explicitly enables only that account
and labels the configuration `synthetic`. It is a test fixture, not an onboarding
shortcut for real records. The generated demo file is ignored by git. After copying it into the runtime
configuration, keep that local runtime change out of commits.

3. Sign in at port 8501, open **Imports**, choose the `synthetic` mapping, select
   `examples/synthetic.csv`, and submit.
4. Expect **3 rows examined, 2 accepted, 1 rejected**. The third amount is
   intentionally malformed. Re-submit the same file to see the original import
   without additional transactions. The worker must be running to complete jobs.

## Approved export format

Exactly five mapped headers are required: date, amount, type, category and provider.
Their source names are configurable. Provider cells may be blank, explicitly
representing practice-level records. Other required values may not be blank.
Known provider and category labels map to pre-provisioned internal UUIDs; the
importer never creates or guesses providers/categories from raw file text.

| Format | Supported contract |
|---|---|
| CSV | UTF-8, optional BOM, configured delimiter, exact headers and explicit date format |
| XLSX | One visible worksheet, one table beginning at row 1, no merged/hidden rows, formulas, macros or external links; dates as configured text |
| PDF | Computer-generated text PDF; each page must yield tables with matching headers; configurable line/text table strategy; no OCR |

Amounts must be literal decimals with at most two fractional digits. Currency
symbols, grouping separators and scientific notation are rejected. Negative
amounts require explicit configuration. Numeric XLSX amounts are read directly
from XML decimal text, avoiding a binary-float conversion. Excel serial dates
are rejected instead of guessed. Blank/malformed data rows are counted as rejects.

Limits: 10 MiB input, 50,000 data rows, 256 characters per cell, 50 PDF pages,
50 MiB expanded XLSX content. Structured PDF extraction is not a guarantee for
arbitrary statement layouts; provide an approved representative sample before use.
PDF prose outside extracted tables is not interpreted as financial records.

## Configure a real clinic later

Answer the unresolved questions in `docs/open-questions.md` first. An operator
must provision approved categories/providers, confirm a single currency and the
negative-adjustment/date conventions, and write explicit profiles and account UUIDs
into `config/ingestion.json`. `Profile` and `IngestionConfig` in
`app/ingestion/config.py` define the validated format. Restart the API to apply
changes. Invalid configuration fails startup instead of falling back to guesses.

Use `mode: clinic` only after scope and access approval and required security work.
The UI checkbox is a per-upload reminder; it does not establish a legal exemption
or prove a file is free of identifiers. The importer retains only allowlisted,
normalized financial fields and fixed rejection reasons. Raw input and original
filenames are never persisted by the application. Metadata stores the file hash
and a generic format filename for provenance.

## API

Sign in using `POST /api/v1/auth/login` with JSON `username` and `password`.
Use the returned bearer token on all other routes.

| Method | Route | Result |
|---|---|---|
| GET | `/api/v1/ingestion/config` | Whether this account can import, available profile names and limits |
| POST | `/api/v1/uploads/{csv,xlsx,pdf}?profile=NAME` | Raw file body; 202 queued, or 200 existing identical upload |
| GET | `/api/v1/uploads/{UUID}` | Uploader-scoped summary and rejection reasons |
| POST | `/api/v1/uploads/{UUID}/retry` | Requeue a failed job; 202 |
| GET | `/api/v1/auth/me` | Current identity |
| POST | `/api/v1/auth/logout` | Revoke current session |
| GET | `/api/v1/health` | Authenticated database health |
| GET | `/api/v1/openapi.json` | Authenticated API schema |

Send raw bytes, not multipart. The API bounds input in memory, checks source
structure and normalizes values before storing anything. This preflight is run
off the event loop. Streamlit submits it in a background thread and remains
responsive. A **separate durable worker** validates catalog references and commits
the facts and final counts. Pending means queued or currently being processed;
a short processing state is intentionally not exposed before the atomic commit.

Structurally unreadable files return a specific 422 reason and are not queued;
row counts are unknown, not fabricated. Row-level errors yield a queued import
whose final accepted/rejected totals account for all extracted data rows.

## Idempotency and retry

A byte-identical re-upload returns the original upload under the same mapping
and uploader. It does not add facts. A different mapping, uploader or deleted
upload state produces 409 without disclosing another user's summary. Repeated
identical rows *within* one file are retained as separate rows, not silently deduplicated.

Changed or overlapping exports have different hashes and can duplicate real-world
transactions. After a partial import, export only the rejected rows for correction;
do not resubmit the already-accepted rows in a changed file. Cross-file transaction
identity requires a stakeholder/source-system decision and is not implemented.

Failed processing rolls back the entire fact-writing attempt. Fix the operational
cause, then retry the same upload using the UI/API. The worker reuses normalized
staged rows; no original file is retained. Completed imports cannot be retried.
Mappings are snapshotted as normalized IDs plus their profile hash, so an in-flight
job never silently adopts a new mapping. Catalog state is checked at execution.

## Verification

```sh
python -m pip install -r requirements-test.lock
python -m pytest -q
```

Without PostgreSQL DSNs, the integration suite explicitly skips. For a disposable
DB initialized by this project's Docker entrypoint:

```sh
docker compose -f compose.yaml -f compose.test.yaml up -d --wait db
```

Set `TEST_MIGRATION_DATABASE_URL` for `clinic_migrator` and `TEST_DATABASE_URL` for
`clinic_app`, pointing to this disposable DB at `localhost:5432` with matching
passwords. Then run pytest. These tests persist synthetic fixtures; never use a
clinic database. GitHub Actions includes the full integration setup and container
smoke checks, but has not been executed in this workspace.

Runtime/test dependencies are pinned in the lockfiles. Docker uses the runtime
lock. Image digest pinning, TLS, encrypted volumes, backups/restore, monitoring,
retention/export/deletion and production runbooks remain Phase 6 work.

## Phase 4: staffing and clinic budgets

The cumulative workspace now includes employee headcount and per-group salary,
benefits and effective payroll-tax inputs, scheduled rent/utilities/software and
other clinic costs, one-time startup costs, historical or manual incremental
revenue, and three-scenario cumulative break-even projections. Configure
`config/simulation.json` access, then select **Staffing & clinic budget** in the
temporary demo UI. Inputs and outputs use the authenticated
`POST /api/v1/simulations/clinic` API for reuse by the final web frontend.
See [the Phase 4 report](docs/phase-4-report.md) for worked examples, configuration,
verification and limitations. Phase 5 has not started.


### Saved budgets and visuals (Phase 4 revision)

Use **Save & calculate** to persist named budgets and result snapshots in PostgreSQL.
**Open saved budget** restores your inputs after signing in again; **Save as new
budget** creates an independent cost plan. Compare up to four saved plans using
named tabs, expected-net bar charts and tables. Each sensitivity tab also shows
monthly and cumulative line graphs, a cost-composition bar chart and payroll/clinic
expense tables alongside the complete assumptions. Unsaved edits are not retained.
Budgets are private to their creator; historical inputs require provider access.

Migration `004_saved_budgets.sql` is required and is applied by the existing
forward-only migration runner. See ADR 023 for snapshots, concurrency checks,
access rules and current verification limits. Phase 5 has not started.


## Phase 5 and reproducible environments

Start with [how-to-run.md](how-to-run.md) for isolated dev/test setup, generated
credentials, dummy data, a local question demo and production prerequisites.
[progress.md](progress.md) records what every phase implemented, why each
architectural decision was made, verification limits and remaining work.

Phase 5 adds authenticated financial questions, six reviewed SQL query shapes,
a dedicated read-only database connection, bound date parameters, grounded result
references, visible SQL/raw results, revision-aware caching, clinic-wide rate
limits and token-cost reporting. Remote LLM use is disabled until explicitly
configured. Dev/test can use a labeled fixed-prompt adapter without external API
calls; staging/production reject it. See [the Phase 5 report](docs/phase-5-report.md)
and ADRs 024–027. The new migration is 005; Phase 6 has not started.
