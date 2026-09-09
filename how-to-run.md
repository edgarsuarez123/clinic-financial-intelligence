# How to run the clinic platform

This guide covers the cumulative Phase 1–5 workspace, React extension, version 0.6.0. Run every command from the project root containing `compose.yaml`. Commands use a POSIX shell; Windows users can use WSL2 with Docker Desktop integration.

**Current boundary:** the local application and test workflows are implemented. Docker, live PostgreSQL and a real LLM provider were not available for execution in the build environment. The commands below are the intended reproducible workflow, not a claim that production deployment has been verified. The React frontend is implemented; Phase 6 hardening remains unfinished. Live model and database execution remain unverified.

## 1. What runs

| Service | Purpose | Data or credentials |
|---|---|---|
| `db` | PostgreSQL star schema, saved budgets, jobs, sessions, query cache and logs | One persistent database volume per environment/project |
| `migrate` | Applies only missing, checksum-verified forward migrations, then exits | Separate migration credentials |
| `api` | FastAPI authentication, imports, analytics, budgets and questions | Restricted application credentials; separate read-only query credentials |
| `worker` | Processes queued normalized imports asynchronously | Application credentials |
| `web` | Primary React web interface, port 3000 in dev | Same-origin proxy to API; no direct database access |
| `ui` | Optional Streamlit demo (`legacy-ui` profile) | API only; no direct database access |
| `tests` | Optional disposable integration-test container | Enabled with the `test` profile; guarded against non-test environments |

The browser UI includes sign-in, analytics charts/tables, imports, saved staffing/clinic budgets and financial questions. React is now the primary web interface; Streamlit is optional.

## 2. Prerequisites

Install Python 3.12 or newer, Docker Engine/Desktop and Docker Compose v2. Docker must be running. Image builds need access to the Python package index and container registry. A real LLM key is **not required** for the local dummy-data demo.

Check availability:

```sh
python3 --version
docker --version
docker compose version
```

Do not export production credentials or environment settings into the terminal used for dev/test. Compose shell variables override values from `--env-file`. If you previously exported the platform variables, clear those exports before the commands below:

```sh
unset APP_ENV CONFIG_DIRECTORY API_PORT UI_PORT WEB_PORT POSTGRES_PASSWORD APP_DB_PASSWORD MIGRATION_DB_PASSWORD QUERY_DB_PASSWORD LLM_API_KEY CONFIRM_DISPOSABLE_TEST_DATABASE
```

## 3. Environment separation

| Environment | Compose project name | API / React / optional Streamlit ports | Data |
|---|---|---|---|
| Dev | `clinic-dev` | 8010 / 3000 / 8501 | Dummy data; interactive experimentation |
| Test | `clinic-test` | 8001 / 3001 / 8502 | Separate disposable database; automated tests |
| Staging | `clinic-staging` | 8002 / 3002 / 8503 | Reserved for a private pre-production rehearsal |
| Production | `clinic-production` | 8003 / 3003 / 8504 in the local scaffold | Reserved for the real clinic after launch gates |

All local bindings are loopback-only. Every environment uses the same source code but has its own generated `.env`, configuration directory, database volume and Docker network. The database is named `clinic` inside each isolated instance; it is not a shared database. Different `-p` names are what separate Compose resources. Use the matching `--env-file` and `-p` on **every** command.

Production should ultimately use a separate host/cloud account and secrets, rather than rely on local project names as its entire isolation strategy. Never copy the production database into dev/test. Promote reviewed code/migrations and approved configuration through environments, not dummy databases or test credentials.

## 4. First dev startup

Create local settings and four independent random database credentials:

```sh
python3 scripts/prepare_environment.py dev
```

This creates `environments/dev/.env` and four disabled configuration files. The secret file is owner-readable/writable only. Generated environments are ignored by Git and excluded from Docker build context. The helper refuses to overwrite an existing directory; do not regenerate credentials when restarting an existing database.

Validate configuration without printing resolved secrets, then start:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev config --quiet
docker compose --env-file environments/dev/.env -p clinic-dev up --build -d
docker compose --env-file environments/dev/.env -p clinic-dev ps -a
```

`migrate` should finish with exit code 0. `db`, `api`, `worker` and `web` should remain running. PostgreSQL bootstrap provisions roles only when the database volume is new; migrations then apply 001–006 in order.

Create a demo login. You choose the password interactively; there is no default password:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev run --rm migrate python -m app.bootstrap demo-owner
```

Initialize dummy dimensions and enable all demo modules for that account:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev run --rm --user "$(id -u):$(id -g)" -v "$PWD/environments/dev/config:/demo-config" migrate python -m app.demo_environment demo-owner --config-dir /demo-config --confirm-disposable
docker compose --env-file environments/dev/.env -p clinic-dev restart api
```

This is a one-time setup on a new disposable database. It requires an existing login, no transaction rows and disabled configuration. It does not silently replace an already configured environment. The generator is blocked outside dev/test. It enables a **local deterministic question demo**, not a paid remote LLM.

Open [the dev UI](http://127.0.0.1:3000) and sign in as `demo-owner` with the password you chose. The API is at [port 8010](http://127.0.0.1:8010). Financial endpoints, including OpenAPI at `/api/v1/openapi.json`, require authentication; a browser visit without a bearer token receiving 401 is expected.

## 5. Exercise the full dummy-data workflow

### Imports and validation

For the fuller clinic example, import `examples/staff-costs.csv` with the
`staff-costs` profile and `examples/medical-billing.csv` with `medical-billing`.
Select March 1, 2025 through August 31, 2026. These contain fictional employees
and payments with real insurer/code labels. Use them instead of the older sample
ledger below to avoid overlapping totals. See `examples/README.md` for details.
The checked-in billing file is a 1,500-row sample. Run
`python -m app.demo_data --full` before import when you want the complete
18-month generated billing volume.

### Upgrade an existing synthetic demo

Fresh demo setup includes these profiles. To extend an existing dev configuration
without deleting transactions or changing account permissions:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev build migrate api worker web
docker compose --env-file environments/dev/.env -p clinic-dev run --rm --user "$(id -u):$(id -g)" -v "$PWD/environments/dev/config:/demo-config" migrate python -m app.ingestion.demo demo-owner --output /demo-config/ingestion.json --confirm-disposable --extend-existing
docker compose --env-file environments/dev/.env -p clinic-dev run --rm --user "$(id -u):$(id -g)" -v "$PWD/environments/dev/config:/demo-config" migrate python -m app.analytics.demo --source /demo-config/ingestion.json --output /demo-config/analytics.json --extend-existing
docker compose --env-file environments/dev/.env -p clinic-dev up -d api worker web
docker compose --env-file environments/dev/.env -p clinic-dev restart api
```

Use your username in place of `demo-owner`. Import the two CSVs through Data
imports afterward. If older overlapping fixtures were already imported, use a
separate fresh disposable test environment for clean totals. Do not reinitialize
or delete a real database.

### Legacy parser fixtures

1. Select **Data imports**, choose mapping `synthetic` and upload `examples/synthetic-history.csv`.
2. Confirm it contains only approved aggregate data and submit. The worker should eventually report **52 accepted, 0 rejected**.
3. Re-upload the identical file. The existing upload should be returned without adding transactions.
4. Upload `examples/synthetic.csv` to exercise rejection handling: **2 accepted, 1 rejected** for the malformed amount. Its January 5–7 dates precede the larger history file's January 12–July 6 range.

The larger fixture contains 26 weeks of synthetic collections and supplies. It is not a complete or realistic clinic ledger, and it does not certify provider cost completeness. No actual salaries, patient records or clinic business assumptions are seeded. Dates are created by the ingestion worker as needed.

### Analytics

Select **Overview** and use `2026-01-01` through `2026-07-31`. Review revenue/expense/net, weekly/monthly tables, growth and moving-average plots, cost breakdowns and volatility. Missing data and partial periods are labeled. Provider contribution may remain unavailable because the dummy expenses are not declared to represent a fully loaded provider cost.

### Budgets and cost alternatives

Select **Budgets & scenarios**:

1. Click **Use current financials** after selecting complete baseline months to carry revenue and costs, including payroll, into a new plan. Alternatively, **Load synthetic example** starts a manual worked example.
2. Name it `Current clinic` and click **Save plan**.
3. Inspect pessimistic/expected/optimistic tabs, line graphs, cost bars, exact tables and adjacent assumptions.
4. Change the name to `Higher rent plus staff`, edit rent/headcount/payroll assumptions, and click **Duplicate**, then **Save plan**.
5. Click **Compare** on each saved plan. Expected-scenario revenue, costs and net appear in bar charts and exact tables grouped by currency; start dates, horizons and full snapshot assumptions stay visible.
6. Sign out, sign back in and reopen either budget. Inputs and saved results should return from PostgreSQL. This does not depend on the prior browser session.

Only **Save plan** persists edits. Duplicate creates an unsaved copy in the editor. Opening a saved budget displays its saved result snapshot; saving again refreshes calculations and any selected historical baseline. Separate open tabs cannot silently overwrite conflicting revisions.

Current-financial baselines are snapshots: choose **Use current financials** again
to rebase a new plan on newer imports. Add only incremental staff and expenses;
existing payroll is already included. Review one-time expenses before carrying
them forward. Monthly averages are rounded to cents; projections do not infer
seasonality. Formulas and full assumptions are expandable. Refresh preserves
the page and revalidates the session, but does not save unsaved edits.

### Financial questions without an external API

The local demo recognizes these exact phrases, also listed in the UI:

- `show the financial summary`
- `show monthly trends`
- `show weekly trends`
- `show the cost breakdown`
- `show weekly volatility`
- `show observed provider totals`

Select the same date range as above, enter a phrase and submit. Submission acknowledges the displayed processing disclosure. For provider totals, choose the provider-financials scope. Inspect the answer, interpretation, SQL, bound dates and raw result table. Repeat the same question to exercise the cache. A new completed import invalidates the previous financial-data revision. The demo usage report should show zero token cost.

This fixed-prompt adapter does not test an actual model's language understanding. An unrecognized question is intentionally refused. Automated tests cover hostile SQL, invalid result references, permission denials and rate limits.

## 6. Run tests in a separate environment

### Fast tests without PostgreSQL

For local development:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.lock
python -m pip install --no-deps -e .
python -m pytest -q -m 'not integration'
```

These use synthetic in-memory doubles where appropriate. They cover calculations, parsing, API access, UI flows, query contracts and environment helpers. They do not prove database grants or actual persistence.

### Full suite with disposable PostgreSQL

Create a completely separate test environment:

```sh
python3 scripts/prepare_environment.py test
docker compose --env-file environments/test/.env -p clinic-test --profile test run --build --rm tests
```

The test service starts its isolated PostgreSQL dependency. Fixtures apply migrations and create synthetic records. It supplies separate `TEST_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL` and `TEST_QUERY_DATABASE_URL` internally, so the database-role tests can run. The runner refuses unless APP_ENV is `test` and the disposable-test flag is true. A nonzero exit indicates a failed test or setup; inspect that before proceeding.

Do not point these DSNs at dev, staging or production. Automated fixtures create and modify records. For repeatable integration runs, use a fresh **test-only** database:

```sh
docker compose --env-file environments/test/.env -p clinic-test down --volumes
docker compose --env-file environments/test/.env -p clinic-test --profile test run --build --rm tests
```

The first command permanently removes the disposable test database. It is not a production upgrade procedure. The test environment is intentionally separate from the interactive dev demo, so resetting it does not erase your dev budgets.

## 7. Enable a real LLM only when explicitly configured

Keep dummy financial data while evaluating a real provider. Before enabling remote operation, obtain the required written disclosure/DPA references, select a compatible endpoint/model, and enter the provider's verified token prices.

In the chosen environment's `config/query.json`, configure:

| Setting | Meaning |
|---|---|
| `enabled` | Explicit true only after setup |
| `transport` | `https_chat` for remote operation |
| `synthetic_data` | True while using dummy records |
| `authorized_user_ids` | Approved question users; analytics access is also required |
| `cost_report_user_ids` | Approved usage-report users |
| `provider_name`, `model` | Chosen provider/model identifiers |
| `endpoint` | Full HTTPS chat-completions-compatible endpoint, without credentials/query/fragment |
| `disclosure_reference`, `dpa_reference` | References to actual reviewed/executed documentation; placeholders do not satisfy the obligation |
| `input_price_per_million`, `output_price_per_million` | Explicit decimal strings, e.g. actual contracted prices—not invented defaults |
| `pricing_currency` | Currency of those prices |
| `requests_per_window`, `window_seconds`, `cache_seconds` | Operational limits |

Set `LLM_API_KEY` in the environment's secret file without committing it. Updating environment variables requires container recreation; a simple restart does not reload the container environment:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev up --build -d --force-recreate api
```

The adapter requests JSON responses and does not follow redirects. Validate the selected provider's support for the request contract. Real questions must stay within the reviewed query catalog. There is no claim of unrestricted SQL support or guaranteed translation accuracy. Verify generated interpretations and results using known dummy examples before considering real clinic data.

## 8. Routine commands and persistence

```sh
docker compose --env-file environments/dev/.env -p clinic-dev logs --tail=100 api worker migrate
docker compose --env-file environments/dev/.env -p clinic-dev stop
docker compose --env-file environments/dev/.env -p clinic-dev start
```

Stopping/restarting preserves the named database volume. `down` without `--volumes` also preserves it, while removing containers/networks. Never use `down --volumes`, delete the database volume or regenerate credentials as an ordinary upgrade.

To upgrade an existing environment with this cumulative workspace:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev up --build -d
```

The normal migration service applies missing migrations and refuses changed historical migration files. Preserve the original `.env`, configuration and volume. Obtain a tested backup before real production upgrades once Phase 6 is implemented. Current environments use distinct secrets; never copy a dev secret file into production.

## 9. Staging and production preparation

You can prepare disabled configuration directories now:

```sh
python3 scripts/prepare_environment.py staging
python3 scripts/prepare_environment.py production
```

That only creates local configuration and secrets. It does not deploy or make the application production-ready. The dummy initializer and local question adapter are blocked in those environments.

Before a real clinic instance is started, finish these existing project gates:

1. Phase 6: TLS for application/database connections, encrypted database/storage, automated backups with a tested restore, uptime/error alerts and operational runbooks.
2. Approved clinic users and compensation permissions, source export mapping, currency/cost basis, historical attribution and no-PHI determination.
3. Data export and an agreed deletion/retention policy, including audit records, cache and backups. Soft deletion is not permanent erasure.
4. Executed LLM agreements/disclosures and a tested provider, or keep remote questions disabled.
5. The final custom frontend, deployment/secret-management decisions and staging acceptance tests.

Then deploy the same reviewed code and forward migrations into a new clinic-specific production instance on the approved host. Use its own `.env`/secret manager, configuration and database. Do not promote a dummy database or reuse demo account UUIDs. Production hosting, TLS/reverse-proxy configuration and backup automation are not supplied by merely setting APP_ENV=production.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Feature disabled | Confirm the correct environment config directory is mounted, setup ran for the correct account, and the API restarted after JSON changes |
| Dummy setup refuses | It requires dev/test, an existing account, an empty transaction table and disabled config; it is not an overwrite/reset tool |
| Import stays queued | Check worker and migration logs; the separate worker must be running |
| Password authentication fails after editing `.env` | PostgreSQL bootstrap passwords apply only to a new volume; changing a file does not rotate existing database roles |
| 401 on API/OpenAPI | Authenticate and pass a bearer token; financial routes are not public |
| Question is refused | Check selected dates, supported catalog/permission scope and currency quality; local demo accepts only listed fixed phrases |
| Question service unavailable | Check query-role DSN, migration 005, provider endpoint/key/model and its supported JSON contract; other modules remain available |
| Saved budget conflict | Another tab saved a revision; reopen the latest budget or save your edits as a new budget |
| Integration tests skipped | Use the test container or configure all three disposable test DSNs; skipping is not a passing database test |
| Bind-mounted config permission error | On POSIX use the documented `--user` option; config files must be readable by the API container user, while secret files stay private |

References: [Compose project names](https://docs.docker.com/compose/how-tos/project-name/), [environment-variable precedence](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), and [Compose down/volume behavior](https://docs.docker.com/reference/cli/docker/compose/down/).


## 11. React frontend and existing-workspace upgrade

The workspace now contains `frontend/`; it uses all implemented Phase 1–5 API modules. The previous `ui/` remains available with `--profile legacy-ui`. React's inputs and results persist only when you click **Save plan**. Reopening a saved plan restores the database snapshot. Refreshing the browser requires sign-in because the bearer token is memory-only.

For an existing dev installation, edit just `API_PORT=8010` in `environments/dev/.env` (and optionally add `WEB_PORT=3000`). Do not regenerate credentials. No environment files existed in the delivered Phase 5 source; fresh ones are created with the helper above.

Rebuild and apply the new forward migration, then rebuild the services:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev build migrate
docker compose --env-file environments/dev/.env -p clinic-dev run --rm migrate
docker compose --env-file environments/dev/.env -p clinic-dev up --build -d api worker web
```

Migration 006 grants the locking privilege needed by login; host port 8010 avoids the reported port 8000 conflict. Open http://127.0.0.1:3000. For React hot reload, follow `frontend/README.md`.

## 12. Genuine local model with Ollama (optional dev/test)

Complete the synthetic user/environment initialization above first. The deterministic adapter is still the default so setup does not depend on model downloads or hardware. To use a real local model:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev -f compose.yaml -f compose.ollama.yaml up -d ollama
docker compose --env-file environments/dev/.env -p clinic-dev -f compose.yaml -f compose.ollama.yaml exec ollama ollama pull qwen2.5:7b
```

With the Python project installed in your local virtual environment:

```sh
python -m scripts.configure_ollama dev --model qwen2.5:7b
docker compose --env-file environments/dev/.env -p clinic-dev -f compose.yaml -f compose.ollama.yaml up --build -d api worker web
```

`qwen2.5:7b` is an explicit example, not a promise of translation quality or a hardware recommendation. Choose another downloaded local model with `--model`. Do not use cloud models or configure the server to relay data externally. Ollama's container has no published host port. The first download requires registry access and disk space; runtime speed depends on hardware. CPU is the portable default; GPU pass-through is not assumed.

For Ollama already installed on your host, use `--endpoint http://host.docker.internal:11434/api/chat` and add `extra_hosts: ["host.docker.internal:host-gateway"]` to the API service on Linux if needed. The host service must accept the container connection; its normal loopback-only listener may not. Prefer the provided container overlay for consistent isolation. When running the API directly on the host, use `http://127.0.0.1:11434/api/chat` instead.

Repeat with `test`, `clinic-test` and its configuration file for an isolated test instance; never reuse dev project/volume names. The Ollama adapter is rejected at API startup in staging/production, even if manually enabled. HTTPS providers retain the existing DPA/disclosure requirements. Local UI disclosures identify Ollama, and usage shows token counts with zero API charge; hardware/electricity costs are not included.

Ask Clarity displays the generated SQL, bound parameters and exact database results. Unsupported translations are refused. The same SQL allowlist, dedicated read-only login, rate limit and cache apply. There is no silent fallback to a paid provider. A model outage leaves other modules available. Increase hardware capacity or choose a suitable smaller local model if generation exceeds the bounded timeout; two model stages can take approximately 150 seconds total.

## 13. React verification and remaining launch gates

```sh
cd frontend
npm ci
npm test
npm run build
```

The UI tests cover decimal-string preservation, large-value formatting, expired sessions, budget revisions and conflict retention. Python tests cover native Ollama response handling, local endpoint restrictions, environment restrictions, truncation/errors and rejection of unsafe model SQL. These checks are separate from an actual Docker/PostgreSQL/model test.

Still required: live migrated-database verification, actual-model accuracy/latency evaluation, browser/accessibility review and the existing Phase 6 TLS, encryption, backups/restore, export/deletion policy and operations work. No production deployment was performed.
# Revenue explorer (migration 007)

Rebuild and apply the migrate image, then rebuild API, worker and web:

```sh
docker compose --env-file environments/dev/.env -p clinic-dev build migrate
docker compose --env-file environments/dev/.env -p clinic-dev run --rm migrate
docker compose --env-file environments/dev/.env -p clinic-dev up --build -d api worker web
```

New synthetic initialization includes a `synthetic-revenue` profile. Import
`examples/synthetic-revenue.csv` with that profile. Do not also import an
overlapping financial dataset as though it were new transactions. The sample
totals $2,802.80: Q1 $1,001.00, Q2 $1,801.80; Demo Health A $900.90,
Demo Health B $1,201.20, unclassified $700.70. The code labels are fictional.

For an already configured demo, add a profile by copying your existing synthetic
profile (preserving its generated category/provider IDs) and adding:

```json
{
  "columns": {
    "date": "date", "amount": "amount", "type": "type",
    "category": "category", "provider": "provider",
    "medical_insurance": "medical_insurance", "billing_code": "billing_code"
  },
  "medical_insurances": {"Demo Health A": "Demo Health A", "Demo Health B": "Demo Health B"},
  "billing_codes": {"DEMO-001": "DEMO-001", "DEMO-002": "DEMO-002"}
}
```

This is a fragment, not a replacement for the complete profile. Existing
date/currency/type/category/provider settings are required. Map real insurer
and code values explicitly when clinic onboarding is approved. Add approved
revenue category UUID/display-label pairs to analytics `public_category_labels`
for individually named category filters; otherwise they show as “Other revenue”.

Open **Revenue explorer**, choose dates and Week/Month/Quarter, and select any
combination of insurer, billing code and revenue category. Every total and
breakdown follows those filters. Empty/old values appear as “Not classified”.
The new fields are available in the explorer, not in the LLM query catalog yet.

CSV columns outside the approved mapping are removed in the React browser
before submission. Use only synthetic identifiers when testing this workflow.
XLSX/PDF and direct API/Streamlit uploads must already be financial-only; export
to CSV locally when necessary. Real patient-containing source workflows require
the ADR 006/032 scope review before release; this feature does not establish
de-identification or production readiness.

### Full React workflow: insurer statements and projections

Use **Data imports**, select an approved mapping including `medical_insurance` and `billing_code`, and choose a text PDF. In the statement layout editor, set the first/last pages and the detail-table top/bottom as page percentages. Map each financial column's left/right bounds; use approved constant values for statement-wide insurer, type and category, and optionally an explicit payment date. Amount and billing code come from the PDF columns. Exclude headings, subtotals and totals; pages in one import must share a layout. Extract locally, review the financial-only CSV, reconcile its payment total, confirm, then validate/import. Patient information must not appear in mapped fields. Scans, rotated pages and ambiguous cells are rejected. XLSX must be financial-only.

Use **Revenue explorer** to combine insurer, billing code, category and date filters and choose week/month/quarter. Each selection updates totals and charts. Use **Budgets & scenarios** to set headcount, salaries, payroll rates, recurring/startup expenses, timing and ramp/multipliers; run or save to recalculate. Duplicate saved plans for alternative costs and compare snapshots. Formula explanations and category cost trends are included. **Ask Clarity** contains the existing question/SQL/raw-results workflow. Chart color controls apply to the current chart session.
