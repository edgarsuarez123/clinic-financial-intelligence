# Focused UI, monthly planning and clinic locations

## Decision

The React overview omits calculation-note banners, window-coverage details and
activity/coverage columns. Percentages display to two decimal places; authoritative
API decimal strings remain unchanged. Seven-day Monday-Sunday weeks are retained.

Ask Clarity no longer has a separate provider scope dropdown. The submitted request
uses the authenticated user's permitted provider access; the server still enforces
the permission. Production/staging responses omit SQL and bound parameters, and
React only displays SQL diagnostics and model usage controls in dev/test. This
updates the original always-visible SQL requirement at the user's explicit request.
Processing disclosure remains visible before a question is sent.

Ollama selects a key from the allowed catalog using structured output. The app
supplies trusted SQL and selected date parameters, then runs the same SQL validation
and read-only executor. This avoids fragile verbatim SQL copying. Failed explanation
generation falls back to facts selected deterministically from already validated
database results. Failed translation or invalid result data still refuses. Model
usage is logged even when narration fails; no numbers are fabricated.

Saved plans accept optional month-specific existing-revenue and operating-cost
overrides. Zero is a real override, not a missing value. Missing overrides inherit
the default monthly input. Scenario multipliers apply after overrides; hire ramp
and one-time costs keep their existing rules. Overrides must be inside the plan/cost
schedule, are retained in assumptions and saved JSON, and use Decimal arithmetic.
Old plans need no rewrite. New calculations use model version clinic-budget-2.

## Locations

Multiple locations within one owner-operated practice share the existing isolated
database and access policy. This is not cross-tenant reporting. An administrator
configures approved location names; an upload is attributed to one selected location.
Historical uploads remain NULL (displayed as Unassigned). The file hash uniqueness
boundary is unchanged: choosing another location cannot bypass duplicate prevention
or silently reassign imported records.

Dashboard, revenue explorer and current-financials baselines can filter by location;
the overview also presents per-location revenue/expense/net alongside combined totals.
Filters are bound SQL parameters. The LLM catalog remains practice-wide and will
refuse location-specific questions; location querying through chat is not yet supported.
Files containing multiple locations must be split into location-specific exports.
Separate deployments are not combined, and no historical location is inferred.

## Verification Limits

Unit/API/React tests cover contracts, decimal calculations, weekend inclusion,
diagnostic visibility, location selection and explanation fallback. Database
integration tests require disposable PostgreSQL. Local mocks do not certify actual
Ollama model performance or Docker deployment; those must be checked on the host.
