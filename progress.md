# Budget workspace and persistent Clarity — 2026-09-11

This is the current implementation status. Earlier dated entries below are retained
as history; their manual-save-only, temporary-UI and one-shot-question limitations
are superseded here. The project remains one React/FastAPI/PostgreSQL workspace.
Production hardening and deployment are still unfinished.

## Implemented and why

- Reorganized budgets into Starting financials, Monthly plan, Scenarios and Compare.
  The monthly grid edits revenue, category expenses and per-person salaries, with
  fill-forward, percentage changes and explicit zero values. The four views reduce
  the long form while keeping the existing payroll, ramp, cost and break-even models.
- Valid inputs autosave with optimistic revision checks and a stable creation ID.
  Edits made during an in-flight save remain in the editor and save next. Network
  failures/conflicts pause saving rather than overwrite newer work. Refresh restores
  a saved plan by URL. Invalid or never-saved inputs are still not durable.
- Saved plans support private, revision-checked soft deletion and restoration.
  Duplicate creates an independent plan. Source deletion does not erase historical
  plan values already attached to a saved conversation.
- Current clinic financials load through an explicit review and remain a frozen
  baseline, including recorded payroll and overhead. Results show changes in net
  relative to that baseline. New staff/cost lines remain additive to avoid counting
  the starting business twice.
- Insurance/code drivers calculate clinic revenue as expected units × collected
  payment with monthly overrides. Driver mode replaces amount-based clinic revenue.
  Additional clinic variable costs apply to that revenue; incremental staff retain
  their own variable-cost rates. Volume/payment sensitivity and hiring payback use
  the same pure Decimal engine. Charts retain category colors and readable values.
- Added PostgreSQL conversations and turns through forward-only migration 009.
  Ownership and current compensation/simulation permissions govern reads and tool
  access. Transactions reserve a message before generation and finish it after;
  no database lock stays open during model calls. Message IDs, hashes and attempt
  tokens prevent duplicate replies and late attempts overwriting retries.
- Clarity now saves history, follows up, reads/compares saved scenarios and proposes
  typed percentage/schedule edits. Applying a draft is an explicit **Open as a new
  plan** action. Provider-specific historical inputs refresh when recalculated;
  the draft identifies that source and potential difference from stored results.
- The LLM selects a reviewed tool/query, never executable SQL or arbitrary formula
  code. Aggregate actuals run through the separate read-only role. New clinic,
  insurance/code and provider-location views expose only approved aggregate fields.
  Numeric calculations come from PostgreSQL/Decimal. Interpretation cites returned
  facts and is labeled as inference; validation does not prove prose semantics.
  SQL/usage remain dev/test-only. Outages preserve completed calculation tables.
- Added a history-gated revenue forecast endpoint and React control, also callable
  by Clarity. Chronological validation compares simple models with a last-month
  benchmark. At least 24 complete consecutive months and eight validation errors
  per requested horizon are required. Estimated ranges are not promised coverage
  probabilities. Short histories use explicit scenario assumptions instead.
- Updated Ollama structured contracts for tool selection and evidence-linked
  interpretation. The deterministic demo supports named test phrases and refuses
  unknown questions; it is not a substitute for real-model evaluation.
- Incorporated the newer GitHub demo-data/Ollama commit without replacing its
  datasets. Updated fixture reproduction checks/documentation for the complete
  29,834-row billing file. Preserved the 150-second per-stage local-model timeout
  and aligned browser/proxy waits and interrupted-turn recovery to six minutes.

See [ADR 036](docs/adr/036-budget-studio-and-conversational-analysis.md) for the
architecture and forecast tradeoffs, [how-to-run.md](how-to-run.md) for migration
009 and the new workflows, and [the verification report](docs/react-verification.md)
for current results. Live PostgreSQL, Docker and Ollama execution remain outstanding;
no production deployment or browser/accessibility certification is claimed.

---

# UI cleanup, monthly scenarios and clinic locations - 2026-09-09

- Removed overview calculation notes, exact-window dropdown, activity/coverage
  columns and the budget formula explainer at the user's request.
- Question-scope dropdown removed. Server provider permissions remain enforced.
  SQL and parameters are excluded from production/staging question responses;
  diagnostic and usage panels are dev/test-only. Result tables use readable
  percentage formatting instead of raw unrounded values.
- Ollama selects an allowlisted query key using structured output, avoiding exact
  SQL-copy failures. Invalid narration falls back to validated database facts;
  invalid translation/results still refuse. Fixed invalid volatility catalog SQL.
- Saved plans now retain per-month revenue and operating-cost overrides, using
  Decimal calculations and explicit zero values. Current-financials import remains
  visible, including an access message when unavailable, and can select a location.
- Migration 008 attributes uploads to configured locations. Existing data stays
  unassigned; file-hash duplicate guards also prevent changing an existing upload's
  location by reuploading. Overview and revenue reports support individual locations
  and combined totals. Separate tenant databases are not combined.
- ADR 035 records the choices and changed UI requirements. Updated how-to-run.md
  documents migration/rebuild, location configuration and monthly scenario use.
- Verification: 32 React tests passed; TypeScript checking and production build
  passed. The backend suite passed 190 tests with 49 PostgreSQL tests skipped.
  Live PostgreSQL, Docker and actual Ollama responses remain unverified. Browser
  screenshot verification could not run because Chromium download was unavailable.

# React frontend and local LLM extension — 2026-09-08

This section supersedes prior statements that a custom frontend is pending. Phases 1–5 remain cumulative in this same workspace. Phase 6 is not claimed complete.

## Implemented and why

- Primary React/TypeScript browser app: login, overview, provider contribution, uploads and polling/retry, persistent budget editor, scenario tabs, saved-plan comparisons, and natural-language questions with SQL/results and usage reports. This removes dependence on the temporary Streamlit product interface.
- Charts and exact tables: trends, cost composition, moving averages, provider costs, cumulative scenario results and comparisons. Sparse values stay missing, not zero. Decimal strings remain authoritative.
- Employee headcounts, individual annual salary/cost inputs, benefits, payroll-tax percentages, clinic operating/startup costs, timing, baseline/incremental revenue and editable three-scenario ramps. Synthetic budget example is offered only in synthetic mode. Saved budgets use the existing database and revision guard.
- Native local Ollama adapter for synthetic dev/test, alongside the deterministic demo and HTTPS adapter. Local use does not weaken the SQL boundary or enable staging/production HTTP models. See ADR 029.
- Port 8010 dev default and forward migration 006 for the login row lock. Existing migration checksums are unchanged. See ADR 030.
- Same-origin Nginx frontend service in Compose, Vite proxy for hot reload, legacy Streamlit behind an optional profile. No separate application workspace or replacement backend.
- Updated run instructions and dedicated frontend guide. New ADRs 028–030 record design choices and tradeoffs.

## Verification

Python suite: 169 passed, 47 PostgreSQL integration tests skipped. React suite: 6 passed. Production frontend build and TypeScript checking passed (see current verification file for final bundle sizes). Adapter tests use simulated HTTP responses; they do not prove actual-model translation quality. Docker, PostgreSQL and Ollama are not installed here, so migration application, container startup, durable database behavior and actual model calls remain unverified. No browser/Lighthouse/field performance measurements were made.

Performance and accessibility values in ADR 028 are targets, not achieved scores. The supplied skill's helper/reference bundle was absent; the attached instructions informed the implementation directly. No clinic stakeholder answers were invented.

---

# Clinic Financial Intelligence — implementation progress

Last updated: 2026-09-08. Current application version: **0.5.0**.

This is one cumulative source workspace. Phases 1–5 are implemented within the boundaries below. **Phase 6 and the custom production frontend are not complete.** “Implemented” means code and tests exist; it does not mean deployment, live database execution or real-clinic validation has been demonstrated.

See [how-to-run.md](how-to-run.md) for isolated dev/test setup, dummy data, commands and production prerequisites. Architectural records live in [docs/adr](docs/adr). Earlier phase reports are historical handoffs; the current decisions below supersede their explicitly identified earlier limitations.

## Status by phase: what was built and why

| Phase | What exists | Why it was built this way | Current verification / limitation |
|---|---|---|---|
| 1 — Foundation | FastAPI `/api/v1`, PostgreSQL star schema, forward-only migrations, authentication, Docker, structured application logging and append-only audit schema | Establish integrity and access boundaries before financial features; one isolated deployment per clinic | Unit/API tests run; actual PostgreSQL and container execution remain unverified here |
| 2 — Ingestion | Pluggable CSV/XLSX/structured-PDF parsers, column mapping, explicit row rejection, normalized durable jobs, separate worker, upload hash uniqueness and summary UI | Different exports need configurable adapters; normalized staging avoids retaining raw files and silently guessing values; background work keeps requests responsive | Parser/malformed-input tests run; real source-system samples, mappings and live worker/database integration are not validated |
| 3 — Analytics | Pure Decimal weekly/monthly revenue/expense/net/margins, moving averages, growth, category shares, fixed/variable costs, population CV and protected provider analytics | Centralize reproducible calculations; preserve unknown/sparse periods and separate provider compensation access | Pure/API/UI tests run; complete provider contribution requires explicit cost-completeness evidence |
| 4 — Staffing and clinic budgets | Per-group headcount/pay/benefits/effective payroll taxes, malpractice/onboarding, custom rent/utilities/software/one-time costs, scheduled hires, three ramp scenarios, historical baseline selection, break-even and visualizations | Model the user's expanded whole-clinic cost question while preventing double-counting baseline staff revenue and bundled costs | Hand-worked break-even and whole-clinic examples pass; rates/curves are user assumptions; Monte Carlo remains a stretch goal |
| 4 correction — Saved budgets | Durable named input/result snapshots, reopen/edit/duplicate, version conflicts, private ownership, named comparison tabs and bar charts | The user correctly rejected losing complete budgets after sign-out; preservation belongs in the MVP | Reopen/duplicate/UI and API contract tests run; actual PostgreSQL durability tests are included but skipped here |
| 5 — Financial questions | Bounded text-to-SQL, dedicated query role, exact SQL allowlist and bound dates, grounded result-cell explanations, SQL/raw results, cache, clinic-wide rate limits and token-cost reports | Quantitative answers must come from SQL, with database privilege boundaries and inspectable evidence | Security/contract/UI/adapter tests run; live provider accuracy/interoperability and PostgreSQL grants remain unverified |
| 5 addition — Environments and documentation | Dev/test/staging/production config generator, separate Compose configuration/ports, guarded test container, 52-row dummy history, local deterministic query demo, this file and run guide | Make the complete workspace reproducible without mixing clinic data with tests or requiring a paid LLM for UI checks | Helper/parser/local-demo tests run; Docker workflows still need execution on a Docker-capable machine |
| 6 — Hardening | Not started | Real deployment needs infrastructure controls, tested recovery and agreed lifecycle policies | Requires confirmation; see remaining work below |

## User-driven changes incorporated

- Kept one cumulative workspace rather than creating disconnected projects for each phase.
- Recorded that Streamlit is for testing/demonstration; the final web application must contain login, visualizations, analytics, budgets and questions through the same backend.
- Expanded a single-hire simulator into a configurable whole-clinic budget, including employee counts, per-group employer payroll-tax assumptions, rent, utilities, software and other costs.
- Replaced session-only budgets with database-backed named documents and saved results. Unsaved edits still need an explicit save.
- Added named cost-plan comparisons alongside pessimistic/expected/optimistic sensitivity tabs.
- Added progress/decision documentation and reproducible environment/dummy-data guidance in Phase 5.

## Architecture decisions and reasons

| ADR | Decision | Reason / important consequence |
|---|---|---|
| [001](docs/adr/001-isolated-python-stack.md) | Single-clinic Python/FastAPI/PostgreSQL/Docker deployment | Hard isolation without logical multi-tenancy or replacing the requested stack |
| [002](docs/adr/002-star-schema-and-money.md) | Fact/dimension star schema; NUMERIC/Decimal money | Efficient aggregation and exact arithmetic; reject fractional-cent facts rather than silently rounding them |
| [003](docs/adr/003-forward-only-migrations.md) | Ordered SQL migrations with checksums and advisory locking | Reproducible schema history; no manual edits, down migrations or application migration credentials |
| [004](docs/adr/004-session-authentication.md) | Argon2id passwords and database-backed opaque bearer sessions | Immediate logout/account revocation without JWT signing-key machinery; no default accounts |
| [005](docs/adr/005-audit-separation.md) | Allowlisted JSON application logs and separate append-only audit schema | Keep sensitive payloads out of operational logs; audit failure blocks success; external audit archival is still pending |
| [006](docs/adr/006-no-phi-scope-trigger.md) | Named scope-change trigger for patient identifiers | Prevent incremental features from silently invalidating the aggregate-only data scope; no blanket legal exemption is claimed |
| [007](docs/adr/007-external-configuration.md) | External business assumptions and access configuration | Avoid inventing clinic costs, taxonomy, ramp curves or stakeholder role assignments |
| [008](docs/adr/008-query-security.md) | Text-to-SQL and separately provisioned query role | Database arithmetic and least privilege; Phase 5 implementation refined in ADRs 024–026 |
| [009](docs/adr/009-deletion-policy-conflict.md) | Keep soft deletion; leave permanent-erasure conflict explicit | A recoverable deleted_at flag cannot satisfy a permanent-deletion promise; agreement needed before Phase 6 |
| [010](docs/adr/010-content-idempotency.md) | Unique per-instance SHA-256 upload identity | Identical bytes cannot create repeated transactions; differently formatted overlapping exports are not automatically deduplicated |
| [011](docs/adr/011-calendar.md) | ISO week/year and Monday-start weeks with explicit date ranges | Prevent cross-year week collisions and avoid inventing a backfill horizon |
| [012](docs/adr/012-safe-staging-and-preflight.md) | Bounded in-memory file preflight; persist normalized rows only | Reduce raw-content exposure; no durable raw-file replay or claim of universal PHI detection |
| [013](docs/adr/013-postgres-durable-worker.md) | PostgreSQL job queue and separate worker | Celery-equivalent durability at this scale without another broker; facts/summary/audit commit together |
| [014](docs/adr/014-strict-format-contract.md) | Strict supported CSV/XLSX/PDF shapes | Refuse unsupported layouts instead of dropping sheets, inferring dates or reading floating-point currency values |
| [015](docs/adr/015-ingestion-access-and-duplicates.md) | Disabled-by-default ingestion and uploader-owned summaries | Least privilege until actual onboarding decisions are provided; changed mapping/owner cannot bypass hash uniqueness |
| [016](docs/adr/016-pure-decimal-analytics.md) | Standard-library pure Decimal analytics and explicit sparse-data conventions | Deterministic independently tested results; unknown periods are not zero |
| [017](docs/adr/017-provider-cost-completeness.md) | Fully loaded provider contribution needs a declared completeness basis | Prevent missing benefits, insurance or overhead from becoming an overstated contribution margin |
| [018](docs/adr/018-analytics-access-and-read-views.md) | General/provider read views and separate application access checks | Restrict compensation detail independently from dashboard access; approved category labels only |
| [019](docs/adr/019-production-web-frontend.md) | Temporary Streamlit; custom production frontend still required | Preserve rapid demos while respecting the user's intended final web application |
| [020](docs/adr/020-exact-api-and-chart-presentation.md) | Decimal-string APIs and bounded integer-cent chart presentation | Keep browser plotting from becoming the source of financial arithmetic; exact tables retain precision |
| [021](docs/adr/021-staffing-and-clinic-budget.md) | Per-person staffing inputs, additive clinic costs and explicit baseline revenue | Support whole-clinic scenarios without payroll/revenue double counting; monthly timing conventions are visible |
| [022](docs/adr/022-simulation-access-and-baselines.md) | Explicit simulation access and server-derived observed provider baselines | Do not let callers spoof derived history or access compensation without authorization |
| [023](docs/adr/023-durable-budgets-and-comparison.md) | Persist named plans/results and protect concurrent edits | Correct the initial session-only limitation; preserve snapshots, duplicate alternatives and compare equal horizons/currencies |
| [024](docs/adr/024-reviewed-text-to-sql.md) | Six reviewed SQL shapes and validated result-cell explanations | Prevent unreviewed SQL and invented financial numbers; narrower than unrestricted text-to-SQL and explicitly advertised as such |
| [025](docs/adr/025-query-role-cache-and-usage.md) | Separate query credentials, revision-based cache, shared rate counter and priced usage records | Enforce read-only privileges, avoid stale/cross-user answers and make known/unknown LLM cost visible |
| [026](docs/adr/026-provider-contract-and-disclosure.md) | Provider protocol plus configured HTTPS adapter and disclosure/DPA references | Avoid vendor SDK coupling and accidental external transmission; agreements and provider validation are not assumed |
| [027](docs/adr/027-isolated-environments-and-local-demo.md) | Isolated environment settings plus dev/test-only deterministic question demo | Exercise the full app with dummy data and no API charges; production cannot accidentally use the demo adapter |

The original session-only decisions in ADRs 021/022 are explicitly superseded by ADR 023. The broad parser-based SQL-validation plan in ADR 008 is superseded by ADR 024's stricter full-statement allowlist. Neither change silently alters historical migration files.

## Data and service boundaries

- Financial facts remain traceable to an upload; migrations 001–005 are cumulative and forward-only.
- Pure analytics/simulation functions have no database or web dependency. API and service code handle authorization, data retrieval and serialization.
- Model-selected financial SQL runs only through `clinic_query`. Application operational writes use `clinic_app`. Schema changes use `clinic_migrator`.
- General question views omit provider identifiers. Provider access requires the existing compensation permission and explicit question scope.
- Saved budgets are private to their creator pending a stakeholder-approved sharing policy. They retain the latest saved revision and result snapshot; full revision-history browsing is not implemented.
- Remote questions are disabled by default. The local deterministic dev/test adapter makes no external calls and is not an LLM accuracy test.
- Questions and usage live in the clinic query log; application logs omit questions, financial bodies and secrets. Audit logs are separate but still share the database failure domain.

## Validation record

Latest full local run: **151 passed, 47 skipped**, with two existing dependency deprecation warnings. The skipped tests require disposable PostgreSQL credentials; some additionally require the dedicated query-role DSN.

Verified here: pure financial calculations, hand-computed break-even, payroll/headcount and cost composition, sparse data, strict parsers, malicious SQL rejection, exact parameter checks, explanation references, access controls, API/cache/rate behavior with doubles, UI submit/reopen/compare flows, HTTP adapter behavior with mocked transport, environment configuration isolation, demo-production rejection and dummy-data parsing. Migration 005 and all six catalog statements parse successfully; Python compilation and Compose YAML parsing succeeded.

**Not verified here:** actual PostgreSQL execution of migrations, read-only grants, transactional durability, worker recovery, real database cache/rate concurrency, container builds/startup, real LLM compatibility/semantic accuracy, staging deployment, production security or restore. Test doubles and SQL parsing do not prove these properties. The new test-container workflow is provided to run the database tests on a Docker-capable machine.

No real clinic data, actual LLM credentials, executed clinic agreements or production deployment were used during this work.

## Remaining work and decisions

### Before real clinic onboarding

The eight SRD Section 12 questions remain unanswered: source system/export format, backfill horizon, separate versus bundled costs, provider attribution, hiring-history evidence, authorized users/compensation visibility, a real hiring validation case and patient-identifier presence. Also confirm currency, refund conventions, period/cost-allocation definitions and saved-budget sharing. Synthetic examples are not stakeholder answers.

### Phase 5 activation/evaluation

Select a remote provider/model and compatible endpoint; record real disclosure/DPA references; configure current token prices and account access; verify translation against representative known-answer questions. Unsupported catalog questions should remain refused. Expanding query scope requires new reviewed SQL and tests. The self-reported confidence threshold alone does not establish answer correctness.

### Phase 6 and launch

Implement TLS deployment, encryption at rest, tested automated backup/restore, uptime/error alerting, externally retained audit records, data export, a resolved retention/deletion policy and runbooks for recovery/reprocessing/credential rotation. Choose/build the final custom frontend and verify staging before production. Container image digest pinning, production secrets and host/network policies are also deployment work. Monte Carlo remains optional stretch work.

**Stop at Phase 5.** No Phase 6 work or production deployment is claimed; advancement requires the user's confirmation.

# September 9 feedback review

Reviewed the uploaded web archive. Applied readable assumption rendering to
React and Streamlit, clarified observed activity versus selected-date coverage,
and restricted model-cost reporting to allowlisted dev/test users at the API.
Production usage logging is retained. Historical-question SQL evidence remains
available. React now explicitly explains that chat is not a budget authoring tool.
See ADR 031 for reasons and the pending insurer/code export mapping and no-PHI
confirmation. No insurer/code ingestion or conversational budget authoring is
claimed as complete.

Verification for this feedback change: Python 173 passed / 47 PostgreSQL tests
skipped; React 8 passed; TypeScript and Vite production build passed;
`git diff --check` passed. No live browser, Docker, database, or Ollama test is
claimed. Initial JS is 66.27 KB gzip; the shared chart chunk is 120.04 KB gzip,
so the 80 KB route target is not met on chart-loading routes. Runtime Web Vitals
and Lighthouse scores remain unmeasured.

# Revenue explorer and source-column handling

Added approved insurer/billing-code mappings, forward migration 007, a restricted
revenue view, and pure Decimal weekly/monthly/quarterly calculations. React now
has insurer/code/category filter dropdowns, chart controls, complete exact-value
tables and explicit unclassified/missing-data handling. CSV extra columns are
removed locally before upload; mapped values are validated without echoing raw
cells. Existing five-column profile hashes and financial-only upload bytes are
preserved. Synthetic revenue fixtures and database persistence tests are included.

The owner confirmed sources may contain patient names. See ADR 032 for this
change to the prior source assumption and the required review before real-data
release. XLSX/PDF browser projection, LLM insurer/code questions, and production
hardening are not implemented. No real clinic profile or legal conclusion was
invented.

Verification: 179 Python tests passed; 48 PostgreSQL integration tests skipped
because disposable database connections are unavailable. All 14 React tests and
the TypeScript/Vite build passed. The new revenue route bundle is 1.86 KB gzip;
shared chart JS remains 120.04 KB gzip. Live browser, database migration, and
real-data deployment verification remain outstanding.

## React workflow completion — 2026-09-09

- Revenue filters retain their choices during loading, clear obsolete totals, and ignore stale responses. Added tests for changed totals and out-of-order responses.
- Charts distinguish categories and financial measures, with per-chart color controls. Scenario cost trends use exact decimal summation before visualization; saved plans still hold full assumptions and results.
- Added visible projection formulas alongside existing headcount, payroll, clinic costs, ramp, sensitivity, save/duplicate/compare controls. Ask Clarity remains available in the full React navigation.
- PDF payment statements now support browser-local extraction with explicit page, table-area and column boundaries, approved constant fields, and financial-row review before upload. Only validated financial CSV is submitted; the original PDF is never sent by this React workflow. This is a configurable text-table importer, not universal insurer-layout recognition or OCR.
- PDFs must contain selectable, upright text and consistent layouts in the selected page range. The user must reconcile extracted payment totals and select actual paid amounts. A representative statement is still needed to validate a real insurer layout; no production mapping has been invented.
- Build and component/parser checks are automated; live browser, PostgreSQL and Ollama validation remain outstanding. PDF code and worker are loaded on demand; PDF route exceeds the original 80 KB route budget (parser ~108 KB gzip plus worker), an explicit functionality tradeoff.

Verification for this change: 21 frontend tests passed and production build passed. PDF.js also decoded a synthetic PDF containing a billing code and exact paid amount in a Node smoke check. Confirmation requires the extracted sum to equal the user-entered statement total. The Python suite was not rerun in this session because pytest is absent from the available interpreter; no backend Python changes were made. End-to-end browser/PDF-worker and real-statement validation remain outstanding.
# React usability and actuals-based scenarios (September 2026)

- URL-based navigation restores the selected page, including back/forward;
  valid tab sessions are revalidated on refresh. Unsaved edits still require Save.
- Display percentages round to two decimal places without changing raw results.
- Formula and coverage explanations are expandable. Ask Clarity no longer has
  acknowledgment checkboxes; submission acknowledges the disclosure and provider
  scope remains explicit and permission-gated.
- Current financials can seed a new saved scenario with monthly revenue and
  category cost averages. Existing payroll is included once; new hires/costs are
  incremental. Source dates and assumptions remain saved with each result.
- Two reproducible import fixtures cover 18 months: 846 staff/overhead records
  and a 1,500-row checked-in insurer/code sample. `python -m app.demo_data --full`
  writes the full 20,299-row generated billing ledger for local volume testing.
  They use 12 fictional employees, six real insurer labels, and five real code
  identifiers. All money values are invented.
- ADR 034 records session-storage tradeoffs, presentation choices and baseline
  rules. `how-to-run.md` includes non-destructive synthetic profile upgrades.
- Live Docker/PostgreSQL validation remains pending. The full Python suite could
  not run here because pytest is unavailable; new pure tests run via unittest.
  Verification: 24 React tests and 4 pure baseline/fixture tests passed; the
  production frontend build passed. The new API access test remains unrun.

## Import mapping and display follow-up

- Removed the implicit first-profile selection that sent realistic samples through
  the legacy DEMO1 mapping. Known sample filenames select dedicated mappings;
  absent mappings require an explicit synthetic configuration upgrade. Unknown
  providers remain rejected and raw cell contents are never echoed in errors.
- Added `scripts/upgrade_demo.sh` to build current images, apply migrations,
  extend existing synthetic mappings and recreate services without deleting data.
  The guide now correctly documents refresh/session behavior and the React port.
- Rounded numeric table presentation and chart tooltips; raw SQL result tables
  deliberately retain exact database values. Added no-cache response handling
  for the web entry point to revalidate deployed frontend code.
- Verification: 26 React tests pass, production build passes, shell syntax and
  git whitespace checks pass. Live Docker upgrades and the user's running
  installation remain unverified.
