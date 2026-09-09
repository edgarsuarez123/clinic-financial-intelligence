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
