# 032 — Insurer/code revenue analysis and local source-column removal

## Context and scope update

The owner confirmed source exports may contain patient names, but wants only
financial data retained. The previous assumption that all source exports are
financial-only no longer holds. ADR 006's scope review is therefore required
before real patient-containing source workflows are released. This change is
implemented for development and review; it is not a HIPAA/de-identification
certification, and production hardening remains unfinished.

## Data boundary

React projects CSV files locally, before the upload request. Only explicitly
mapped financial columns are included; all other columns and their values are
excluded. Local validation checks mapped dates/amounts and administrator-approved
type/category/provider/insurance/code values before sending. Invalid mapped
values produce a row number and generic reason, not the cell content. Names
must not be configured as financial field aliases or allowed payer/code values.
No source value preview, browser storage, or telemetry is added. JavaScript
memory erasure is not guaranteed. The browser handles the source transiently.

The API still rejects every unexpected header. It receives and queues only the
validated financial records, with no caller filename. XLSX/PDF projection has
not been implemented in the browser: those files must be financial-only or
exported to CSV locally before use. Direct API and Streamlit uploads must also
be financial-only. Never upload a patient-containing file to the server expecting
the parser to remove its identifiers afterward.

The no_phi_confirmed flag is not evidence that arbitrary patient-linked source
rows are de-identified. Dates, codes, small groups, and other remaining fields
need review in the actual data context. No production configuration is enabled
or safeguard relaxed by this implementation.

## Revenue model

Migration 007 adds nullable medical_insurance and billing_code labels to facts.
These are compact, administrator-approved categorical attributes, not patient
identifiers or free-text notes. Dedicated dimension tables can be introduced if
these categories gain independent metadata; they are unnecessary for label-only
filtering at single-clinic scale. Blank and historical values stay unclassified.
Code systems/modifiers are not guessed or validated against a fabricated code
catalog; the clinic must explicitly approve its codes and financial mappings.

A restricted revenue-only view exposes no provider identities, compensation,
upload contents, or raw category labels. General analytics authorization and
audit logging apply. Category labels use the existing public-label allowlist.
The model query role gets no new grant or catalog query in this change.

Pure Decimal calculations produce Monday-based weeks, calendar months and
calendar quarters, with partial-date labels and explicit missing periods.
Insurance/code/category filters intersect. Each breakdown partitions the same
filtered revenue; breakdowns must not be added together. Collections versus
billed charges is an explicit source mapping choice; revenue is not profit.

## Idempotency and limits

The original five-column profile hash and financial-only CSV bytes remain
unchanged. When extra CSV columns exist, the canonical projected CSV is hashed;
changes only to excluded values produce the same projected payload. This does
not solve overlapping/edited financial exports or deduplicate distinct financial
rows. Existing migrations are not modified and historical codes are not inferred.

## UI

Revenue explorer includes readable money, named periods, insurer/code/category
dropdowns, reset, line/bar trends, ranked horizontal bar charts and full tables.
Top 5/10/20 controls affect only charts; every group remains in the table.
Filters are session-local view preferences, not saved budget edits.
