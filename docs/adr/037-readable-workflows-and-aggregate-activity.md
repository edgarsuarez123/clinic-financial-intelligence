# 037 — Readable workflows and explicit appointment aggregates

Status: accepted implementation scope, 2026-09-12.

## Context

The owner reported congested budgets, unclear financial labels, an unusable chat
experience and a need to reload after imports. The requested Patients tab adds a
different data question: appointment counts by category and period. Financial rows
do not establish visit counts or unique patients.

## Decisions

- Keep React/FastAPI/PostgreSQL; fix behavior and presentation in the actual app.
  Extract reporting/import screens from the application shell so shared navigation
  and data-refresh logic have one owner. No preview-only replacement is acceptable.
- Use plain labels and optional help. Progressive disclosure reduces form density
  without deleting payroll, monthly edits, revenue drivers or saved-plan features.
- Treat successful import completion as a data-change event. Refetch metadata and
  reports; follow expanded dates only when the user was viewing the full available
  range. A narrowed selection remains a deliberate user choice.
- Keep document interpretation explicit. Supported text PDFs can become a reviewed
  financial CSV; missing type/category requires a mapped column or deliberate
  approved whole-document value. Never infer financial type from signs or a model.
  Original patient columns stay local and out of the uploaded financial projection.
- Show each question immediately with a distinct pending assistant reply. Persistence,
  reply identity, retry and chronological rendering are separate responsibilities;
  failed generation must not masquerade as a completed financial answer.
- Store appointment activity separately from financial transactions. Appointment
  counts are supplied aggregates, not inferred from billing rows, codes or units.
  Unique patients remain unavailable without a distinct, vetted source measure.
  Separate optional billed/collected amounts do not augment the financial ledger.
- Reuse configured access, clinic names, append-only audit and forward-only migrations.
  No new patient-identifier storage or real EHR connection is authorized by this UI
  request. Real export mappings still require a representative approved source.

## Verification boundary

The preceding release's GitHub run executed 262 Python tests successfully against
PostgreSQL. Its container check then failed on an uncaught connection reset during
startup. That proves a flaw in the smoke-check retry path, not a diagnosis of every
reported runtime problem. A bounded readiness test must tolerate transient resets
but reject unexpected anonymous API success and persistent failure. Unit tests,
database tests, container startup and live Ollama/browser use are distinct gates.

Detailed workstream ownership and acceptance tests are recorded in
[the implementation plan](../implementation-plan-2026-09-12.md).
