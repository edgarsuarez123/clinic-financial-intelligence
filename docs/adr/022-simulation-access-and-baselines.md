# ADR 022 — Explicit simulation access and historical provenance

Accepted for Phase 4. A separate configured simulation allowlist controls modeled compensation and budget access, defaulting to no users. Historical provider baselines additionally require the existing provider-compensation permission before any data read. Authentication and successful audit recording are required; audits record action and outcome, not entered salaries or projections.

Manual revenue requires an explicit amount and explanation. Historical revenue is computed server-side from the existing protected analytics repository: mean revenue for observed provider-months in fully selected calendar months. Missing months are excluded and counted, not silently treated as zero. Every selected provider needs observations. The response includes observations, date window, missing counts and limitations. The caller cannot supply a claimed historical amount. Currency mismatches are rejected. Using observed revenue for a prospective hire remains an assumption, without inferring FTE, specialty or data completeness.

The Streamlit page is a temporary demo client of the API. The custom production web frontend remains a pre-launch requirement. Synthetic examples are explicitly loaded and are not default clinic inputs. Plans are session-only; reopening the app does not restore a saved budget.


Update: ADR 023 supersedes this record’s session-only storage decision with durable named budgets and saved result snapshots.
