# 031 — Separate clinic presentation from technical evidence

## Context

The September 9 web archive requests insurer/code revenue breakdowns, clearer
data coverage labels, developer-only model costs, readable budget assumptions,
and clarification of conversational budget capabilities.

## Decisions

- Render complete assumption snapshots as readable nested fields in React and
  path/value tables in Streamlit. Preserve decimal strings and all inputs;
  never substitute current edits for the calculated snapshot.
- Explain activity and selected-date coverage separately. Neither guarantees
  complete imported data. Keep missing periods distinct from zero values.
- Restrict the model-cost API and its visibility flag to dev/test AND the existing
  authorized-user allowlist. Production query usage continues to be logged.
  This is environment gating, not a claim that every dev user is a developer.
- Keep SQL and raw database results for historical questions as required by F4.5.
  Budget assumption JSON was not SQL. Do not remove query evidence globally.
- Clearly state that chat cannot create/edit/compare budget plans yet. Existing
  deterministic simulation functions remain the calculation boundary. A future
  conversational planner needs validated draft inputs, user confirmation before
  saving, and explicit missing-input prompts, not model-invented costs or math.

## Pending input

Insurer/billing-code ingestion is not implemented in this change. The current
five-column parser deliberately rejects unapproved headers. Before defining
new mappings and forward-only schema changes, obtain an example header and
synthetic rows, identify the billing-code system, and confirm that rows are
aggregate financial totals without patient identifiers. Do not accept patient
claims or relax no-PHI validation to satisfy a presentation request.

## UI validation targets

Retain the authenticated Vite SPA; assume desktop/corporate connectivity.
Targets: p75 LCP 2500 ms, INP 200 ms, CLS 0.1; initial JS 200 KB gzip plus
80 KB per route; Lighthouse accessibility 95 and performance 90; WCAG AA.
Accessibility ownership is unassigned. Browser measurements are not yet made.
