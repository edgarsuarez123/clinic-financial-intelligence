# Analytics API contract

All endpoints are authenticated under `/api/v1/analytics`. Monetary values,
percentages, averages and CV values are JSON **decimal strings or null**, never
binary JSON floats. Counts are integers and dates are ISO calendar dates.
OpenAPI contains DashboardResponse, ProvidersResponse and MetadataResponse models.

| Endpoint | Permission | Purpose |
|---|---|---|
| GET /config | Signed in | General/provider access flags and synthetic-data label |
| GET /metadata | General analytics | First/last available dates and count of retained completed-import facts |
| GET /dashboard?start=YYYY-MM-DD&end=YYYY-MM-DD | General analytics | Summary, weekly/monthly series, moving averages, category mix, volatility and data notes |
| GET /providers?start=YYYY-MM-DD&end=YYYY-MM-DD | Separate compensation access | Attributed revenue/expense and, where confirmed, fully loaded cost and contribution |

General output never contains provider IDs or labels. Only explicitly approved
public category aliases are exposed; other expense categories are combined by
fixed/variable type. This prevents direct provider labeling; aggregate totals are
not intended to prevent all inference in a small clinic.

A period contains `observed` and `partial` separately. `partial` means that the
selected dates trim a calendar period; an untrimmed period is not a claim that
all source records were supplied. Missing periods have null financial results.
Moving averages include observed/calendar/target counts and `complete_window`.

Provider results contain `attributed_expense`, `fully_loaded_cost`, `contribution`,
`contribution_margin_pct`, `cost_complete`, `cost_basis` and `status`. The latter
three financial values are null until configured completeness covers the selected
range. Practice-level expenses are returned as unattributed, never spread across
providers automatically.

`config/analytics.json` configures authorized account UUIDs, a subset with provider
access, public category aliases, provider labels and `fully_loaded_cost_coverage`.
Each coverage entry is keyed by provider UUID and requires `start`, `end` and an
explicit `basis` explaining the complete attributed cost data. Do not use this
flag to substitute for missing costs. The operator must verify the underlying
records first. Restart the API after configuration changes.

Stable errors: 401 unauthenticated; 403 permission denied; 422 invalid date range,
`currency_unconfirmed`, `range_too_large` or `inconsistent_classification`.
Responses are non-cacheable, and every repository read records a separate audit
event before the response is returned. No live LLM or other external calculation
service is involved.
