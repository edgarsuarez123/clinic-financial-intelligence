# Phase 4 handoff — staffing and clinic budgets

Cumulative Phases 1–4, in one workspace. Phase 5 has not started.

Built: pure Decimal staffing and whole-clinic projections; employee groups with headcount, separate salary, benefits, effective employer payroll tax, malpractice, other fixed costs, onboarding and revenue-variable costs; scheduled recurring and one-time clinic costs; explicit baseline versus incremental revenue; three-scenario piecewise ramp sensitivity; cumulative and sustained break-even; historical provider revenue baseline with provenance; protected audited API and temporary Streamlit budget editor with adjacent full assumptions.

A single incremental staff group with zero existing revenue models a standalone hire. Empty staff and explicit operating costs model a new clinic without employees. Add arbitrary cost rows for rent, utilities, software, insurance or startup costs. All monetary API values are decimal strings. See `config/simulation-example.json` for the complete request contract and the authenticated OpenAPI endpoint for field schemas.

## Hand-computed validation

Hire example: salary 12,000/year = 1,000/month; onboarding 1,000 once; mature revenue 2,000/month; month 1 productivity 50%, then 100%; other costs explicitly zero. Monthly revenue is 1,000, 2,000, 2,000; cost is 2,000, 1,000, 1,000; cumulative net is -1,000, 0, 1,000. Break-even is the close of month 2. The unit test asserts these exact results.

Clinic example: two employees at 60,000 annual salary each, 20% benefits and 10% effective employer payroll tax produce 13,000 monthly staff cost. Rent 2,000, utilities 300 and software 200 bring recurring costs to 15,500. Against 20,000 monthly revenue, recurring net is 4,500. A 5,000 initial cost makes month 1 net -500; cumulative break-even occurs in month 2. All rates and amounts are synthetic, not clinic or jurisdiction facts.

## Configuration and use

Set `config/simulation.json` authorized_user_ids to approved account UUIDs and restart the API. For synthetic testing, explicitly set synthetic_data to true. The composed API already reads this file. Historical revenue also requires analytics compensation access. Real role permissions and clinic inputs remain stakeholder decisions.

Sign in, choose **Staffing & clinic budget**, enter rows and assumptions, then calculate. **Load explicitly synthetic example** provides an editable worked example. Results reflect the last submission; recalculate after edits. Budgets are saved in PostgreSQL using **Save & calculate**. Reopen and edit them after signing in again, or use **Save as new budget** for a separate cost plan. Unsaved edits still require saving. User-entered cost basis must explain whether costs are separate or bundled to avoid counting them twice.

## Verification and limits

Full suite after the persistence correction: 125 passed, 32 PostgreSQL-dependent tests skipped; two existing dependency deprecation warnings. Includes an end-to-end Streamlit test through the authenticated API, monthly and cumulative line charts, cost bar charts, named comparison tabs and adjacent assumption panels; Decimal, payroll/headcount, staggered schedules, double-count prevention, sparse historical data, permission denial before reads, currency rejection and fail-closed auditing tests.

Docker and PostgreSQL are unavailable here; container and live database integration remain unverified. No real clinic data was used. Streamlit remains temporary; the final custom web frontend is still required before launch. Effective payroll percentages do not implement tax-law calculations or payroll processing. Ramp curves are assumptions. Monte Carlo is deferred as the specified stretch goal. Phase 5 requires confirmation.

## Persistent-budget correction

The initial Phase 4 handoff kept budgets only in the UI session. The user rejected that limitation. Migration `004_saved_budgets.sql`, ADR 023 and version 0.4.1 add durable named input/result documents, reopen/edit/duplicate, optimistic revision checks, idempotent save retries and audited per-account access. Run the normal forward migration service before starting the revised app (`docker compose up --build -d` on the configured deployment).

Saved results are snapshots with full assumptions and model version. Opening one does not silently recompute it; Save & calculate refreshes it. Shared clinic-budget permissions and revision-history browsing have not been invented or added. Budgets are private to the creator; explicit sharing can be specified later. Previous-session-only descriptions in ADRs 021–022 are superseded by ADR 023.

Tests verify save/reopen using a new API/UI instance, duplicate isolation, update conflicts, exact retries, ownership and permission denial, and visual comparisons. Four additional real-PostgreSQL tests cover durability across repository instances, transaction rollback on audit failure, database privileges/soft deletion and historical-access revocation. They are present but skipped here because no disposable database is configured. Therefore actual PostgreSQL execution/durability and container deployment are still unverified in this environment; SQL syntax parsing succeeded.
