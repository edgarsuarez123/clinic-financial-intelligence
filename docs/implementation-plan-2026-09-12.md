# Implementation plan — usability, working workflows and appointment activity

Source: the owner's September 12 issue list. This plan is the implementation
contract, not a claim that the changes or production deployment are complete.

## Ownership and sequence

The primary agent owns architecture, data definitions, shared application wiring,
integration, security/financial review and release decisions. Five Luna agents at
maximum reasoning effort implement bounded workstreams below. They must not push,
rewrite historical migrations, weaken access controls, or silently choose clinic
business rules. Each supplies focused tests and a report of remaining limitations.

1. Inspect current code and the latest GitHub/CI state; preserve all existing work.
2. Record this implementation plan and define cross-module contracts before delegation.
3. Implement the five independently owned workstreams in parallel.
4. Integrate navigation, post-import invalidation, configuration and worker wiring.
5. Run focused tests, complete frontend/backend suites and production build. Review
   actual failure logs and run GitHub's database/container workflow when published.
6. Record verified results and remaining blockers in progress.md and the run guide.

Baseline: current remote main is 6a085105cc83a059b11f2a5aa18117e9406e1bd6.
Its CI run passed frontend tests/build and PostgreSQL-backed Python tests, then
failed the API-container smoke test. The cause must be diagnosed from logs; it is
not yet evidence that the deployed UI failure has a single known cause.

## 1. Overview and revenue explorer — reporting agent

### Problem and implementation

- Replace technical labels such as `average_4`/`average_12` with “4-week average”
  and “12-week average,” including readable chart legends and exact table headings.
  These smooth short-term changes using existing calculations; no arithmetic change.
- Rename cost structure/volatility sections using plain business language. Provide
  short optional help explaining fixed versus variable expenses and week-to-week
  variability, not permanent explanatory banners. Do not present variability as risk
  probability or claim complete costs from incomplete records.
- Suppress the redundant revenue-category breakdown when the available dataset has
  only one category. Hide its filter only when there is no active filter to clear;
  preserve active selection/reset behavior. Other insurer/code breakdowns remain.
- Preserve two-decimal percentages, seven-day weeks, location filters, color controls,
  exact monetary values and empty/sparse-data behavior.

### Acceptance tests

No raw `average_4` or `average_12` in visible labels. Optional help explains both
windows. Single-category data does not render a redundant category card. Multiple
categories restore it. Active filters stay clearable and immediately update results.

## 2. Budgets and scenarios — budget agent

### Problem and implementation

- Reproduce save/run/open failures, including required inputs hidden by inactive
  tabs, generic validation errors, concurrent saves and stale displayed results.
  Fix discovered causes with regression tests; do not call a redesign a runtime fix.
- Replace oversized top navigation and permanently expanded saved-plan/form sections
  with a compact workspace switcher and a deliberate plan chooser. Use progressive
  disclosure for staff groups, operating costs and advanced assumptions. Keep the
  monthly grid horizontally scrollable with readable row labels and keyboard access.
- Keep the primary task and current save status visible: starting financials, monthly
  editing, scenario inputs and results. Offer clear labels for multipliers and units.
- Retain baseline review/snapshot, autosave/retry, revision protection, duplication,
  recoverable deletion, monthly overrides, revenue drivers, hiring ramp/payback and
  comparison capabilities. Do not silently remove features to reduce congestion.
- Surface actionable input errors near the relevant field/section. Navigation/opening
  another plan must not discard unsaved edits without warning.

### Acceptance tests

Create a manual plan, load current financials, edit a future month's expense/salary,
calculate, autosave, refresh/reopen, duplicate, compare, delete and restore. The
original plan remains unchanged after duplication. Editing non-visible sections must
not cause a browser “invalid form control is not focusable” failure. Existing Decimal
worked examples and revision-conflict tests continue to pass.

## 3. Imports and immediate refresh — import agent plus primary integration

### Problem and implementation

- Extract the import screen into its own component. It accepts
  `config` and `onCompleted(upload)`; call the callback exactly once per completed
  upload observed during this mount, including an already-completed duplicate.
- On completion, the app refreshes reporting metadata, available date bounds,
  clinic options and mounted reports without requiring a browser reload. Extend a
  selection following the prior full available range, but preserve deliberately
  narrowed user dates. Use a shared revision signal/event and ignore stale responses.
- Preserve CSV/PDF local-only projection and reconciliation: original patient fields
  must not be uploaded simply because financial columns are unclear.
- Add a reviewable local column-mapping step for supported CSV/text PDFs. If a
  document lacks a revenue/expense column, require an explicit whole-document choice
  or approved mapping. If category is absent, require an explicit approved category.
  Never guess either from signs, names, codes or an LLM. Mixed documents require a
  mapped per-row value; do not label a mixed statement automatically.
- PDF extraction can produce a reviewed financial-only CSV, not promise extraction
  from arbitrary layouts or scanned pages. Retain row reconciliation, approved value
  lists, clear validation errors and idempotency. A changed projection may have a new
  content hash; warn that overlapping revised exports are not automatically deduped.

### Acceptance tests

Completed import updates available data/date range without page refresh; failed or
pending import does not announce fresh data. Duplicate completion is not repeatedly
notified by polling. Test missing type/category with explicit user selection, mixed
rows, rejected unknown values, excluded identifier columns, PDF review invalidation
and repeat uploads. No raw document content appears in logs or errors.

## 4. Ask Clarity — conversation agent

### Problem and implementation

- Diagnose create/send/reply/reopen failures across API, adapter and React state.
  Check persistent message schema, retries, provider unavailability, timeout behavior
  and how structured tool selections fail. Do not replace production calls with demo
  answers or loosen the reviewed-query/permission boundary to make responses appear.
- Render a conventional chronological conversation: distinct user/assistant bubbles,
  immediate visible user message, an assistant pending indicator directly underneath,
  then that response's answer/chart/table. Keep the composer accessible and the thread
  list compact/collapsible; scroll the new message into view without stealing input.
- Keep failed turns visible with a clear recovery action; no disappearing questions,
  duplicated sends or unrelated stale replies. Preserve thread history and context.
- Keep production SQL/token-cost panels hidden. Display plain errors that distinguish
  invalid request, missing setup, unavailable model and insufficient data where known.

### Acceptance tests

Question becomes visible before the API reply; reply follows the correct question.
Rapid submit/retry cannot duplicate a turn. Refresh restores completed/pending turns.
Network loss and failed model/tool selection show a recoverable state. Ollama tests
validate structured contracts, not claim live model quality. Existing permissions,
read-only query execution, exact values and saved-plan draft confirmation remain.

## 5. Patients & activity — appointment agent

### Data contract: explicit counts, not inferred identities

The UI may be named “Patients & activity,” but its implemented measure is appointment
volume. Financial transaction rows, procedure units and appointments are different
quantities. Unique patients require separately validated distinct-person aggregates;
that measure is unavailable in this release and must not be mislabeled as appointments.

Use a separate approved aggregate import with date, clinic location, appointment
category and nonnegative integer appointment_count. Categories initially include new
patient, radiology, lab, follow-up, preventive and other, with explicit source mapping
and readable labels; mappings are configurable rather than inferred from billing codes.
Billed amount and collected amount are optional separate Decimal fields. Missing
amounts remain unknown, not zero; average amounts need explicit coverage. No names,
birth dates, patient IDs or free-text clinical notes are retained. Unknown columns
and categories cannot silently become patient data or guessed classifications.

### Implementation

- New `app/appointments/` API, pure aggregation functions and repository; migration
  `010_appointment_activity.sql` is reserved for this workstream. Reuse existing
  authenticated analytics/read and ingestion/write permissions, clinic lists and
  separate audit logging. Record the policy; do not grant all users access.
- Normalized aggregate imports use content hashing, atomic persistence and queued
  processing consistent with existing ingestion. Provide a worker hook for primary
  integration. Repeating the same batch must not add counts. Edited overlapping
  reports still require explicit source replacement/reconciliation, not hidden guesses.
- Add a dedicated React activity screen with week/month/quarter and clinic/category
  selectors. Display appointments, matched-prior-period comparison, category bars,
  trends and exact tables; label partial/unknown periods honestly. Show billed versus
  collected amounts distinctly, without adding either to existing financial revenue.
- Provide an explicit synthetic aggregate fixture/template and setup documentation.
  The real appointment-export format is still unknown; connector/EHR integration,
  arbitrary source PDFs and identified-patient records are outside this implementation.

### Acceptance tests

Hand-computed count and money totals, seven-day weekly boundaries, month/quarter
comparisons, filters, zero counts, missing amounts, unknown categories, incomplete
comparison periods and duplicate batches. Permission denials and audit rollback are
tested. The UI never displays “unique patients” using appointment or billing-row counts.

## Primary-agent integration and release gates

- Own `frontend/src/main.tsx`, global navigation/data revision wiring, `app/main.py`,
  shared worker wiring, CI workflow diagnosis, this plan, progress.md and how-to-run.md.
- Each agent owns separate component/style/test files; communicate shared contract
  changes before editing another workstream. Avoid competing writes to global CSS.
- Review migrations for grants, soft deletion, idempotency and audit atomicity;
  all financial arithmetic remains Decimal and no LLM-generated SQL is executed.
- Run all available automated tests and build. Check the failing container smoke
  step against actual logs and correct its cause. Browser interaction checks, when
  available, should exercise the reported flows, not just a static screenshot.
- Publish only the reviewed integrated tree; preserve newer remote changes and use
  a non-forced update. Report live-model/browser/production gaps separately from
  passing unit or simulated UI tests. No customer deployment is implied.
