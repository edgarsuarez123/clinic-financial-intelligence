# Phase 2 handoff

Scope: ingestion only. Phase 3 has not started. Source SRD author: Edgar J. Suárez Colón.

## Requirement coverage

| Requirement | Implementation |
|---|---|
| F1.1 CSV/XLSX | Authenticated raw-byte upload API and Streamlit uploader |
| F1.2 structured PDF | pdfplumber table adapter; image-only and unextractable pages rejected |
| F1.3 validation | Exact headers, required values, explicit dates/types, Decimal amounts, category/provider mapping; database catalog checks before facts |
| F1.4 rejection reasons | Stable code, source row, safe location and human-readable reason; raw rejected values are not stored |
| F1.5 summary | Total/accepted/rejected counts and reasons; unreadable files return a file-level reason with no invented counts |
| F1.6 clinic mappings | Validated external JSON profiles, single-currency constraint, explicit internal IDs; no source code change for mapping changes |
| F1.7 asynchronous UI | Background UI submission, off-event-loop preflight, durable PostgreSQL queue and separate worker, progress polling |
| F1.8 idempotency | Unique content hash and source-upload/source-row constraint; duplicate resolution; atomic persistence and retry |
| N6.1 pluggable parsers | Common Parser interface and registry |
| N6.9 background jobs | Separate worker process; transaction locks with SKIP LOCKED |
| N6.5 migrations | New forward-only 002 migration; 001 unchanged |

## Validation actually executed

- **68 tests passed; 24 PostgreSQL integration tests skipped.**
- Tests cover CSV malformed rows, no silent blank-row loss, explicit mappings,
  XLSX literal decimal extraction, formulas and extra-sheet rejection,
  structured PDFs, image-only/unstructured PDFs, unauthorized uploads, sanitized
  failures, oversized requests, pending/duplicate responses, and Streamlit
  sign-in/unconfigured-account rendering.
- Both SQL migrations parse; YAML configuration syntax and Python compilation pass.
- No real clinic data was used.

## Unverified gates

This workspace has neither PostgreSQL nor Docker. The 24 skipped tests include
Phase 1's 18 database checks plus six new ingestion checks: identical-file fact
state, concurrent submissions/workers, forced rollback and retry, uploader scoping,
missing catalog references, and mapping-change conflicts. Test doubles do not prove
PostgreSQL idempotency. Run these tests and the supplied container smoke workflow
before calling the integration validated. Docker UI/worker startup and a live
browser end-to-end upload are also unverified here.

## Decisions and assumptions

No Section 12 answer was invented. Real ingestion remains disabled by default.
Synthetic demonstration values are explicitly identified as fixtures. JSON mappings,
source-format limits, decimal/date strictness, queue choice and privacy-preserving
staging are engineering choices recorded in ADRs 012–015.

The API performs bounded in-memory extraction/normalization before enqueueing;
therefore acceptance latency includes preflight. This avoids durable raw-file
staging. Database reference validation and financial persistence are decoupled
from the request in the durable worker. The UI stays responsive during both.

Only the uploader may view a summary or retry it, and only explicitly configured
accounts can ingest. This temporary least-privilege access rule does not decide
the clinic's eventual owner/manager/provider compensation policy.

## Scope limits

- One worksheet per XLSX, text dates, literal values; no inference or OCR.
- PDF support depends on the actual export layout; prose outside tables is not analyzed.
- Byte-level idempotency does not detect overlapping or reformatted exports.
- Raw input and original filenames are not retained; provenance uses hash and upload ID.
- No original source is available for replay under a different mapping. New corrected
  rows need a new upload; failed normalized jobs can be retried as-is.
- Parsing resource limits are present, but dedicated parser process isolation,
  strict CPU timeouts and network ingress limits remain hardening work.
- The raw HTTP body is held briefly in memory; this is not a certification that
  an upstream sender cannot submit identifiers. Scope approval is still required.
- Staged normalized records are financial data and still require Phase 6 encrypted
  storage, retention, backup and operational controls before real use.

## Next stakeholder inputs

Before enabling real clinic imports, obtain the billing system/export format,
an explicitly sanitized representative sample, whether documents can contain
patient identifiers, and the authorized users. Backfill range, currency/date and
negative-adjustment conventions, categories and provider IDs must also be explicit.
Stop for confirmation before Phase 3.
