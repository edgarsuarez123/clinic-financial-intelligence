# Phase 3 handoff — financial analytics

This is the cumulative Phase 1–3 workspace. Phase 4 has not started.
Streamlit remains a temporary demo interface; the final custom web frontend is
required before launch (see product-architecture.md).

## What was built

| Requirement | Implementation |
|---|---|
| F2.1 weekly/monthly revenue, expense, net and margin | Pure Decimal summaries and calendar period series |
| F2.2 4/12-week moving averages | Revenue and expense averages, with observation counts and complete-window flags |
| F2.3 week/month growth | Revenue and expense growth for adjacent observed, untrimmed periods |
| F2.4 category percentage of revenue over time | Category amounts/percentages in overall, weekly and monthly summaries |
| F2.5 provider contribution margin | Protected endpoint; observed attributed costs shown separately; full contribution requires explicit cost completeness for the selected dates |
| F2.6 coefficient of variation | Population standard deviation / absolute mean, using eligible weekly observations |
| F2.7 fixed/variable costs | Overall and period-level exact totals |
| F2.8 sparse data | Unknown periods, partial-period flags, short-window averages, null undefined ratios and explicit empty states |

New read views, separate API access checks, exact-string financial JSON and
OpenAPI response contracts support the eventual production frontend. The temporary
Streamlit dashboard includes period charts, tables, moving averages, expense mix,
volatility and a separately permissioned provider panel. The original import UI
remains available in the same application.

## Validation

- **105 tests passed; 28 PostgreSQL integration tests skipped.**
- Worked examples verify exact totals, margins, growth, 4/12-week averages,
  fixed/variable costs, category percentages, a hand-computed CV of 0.5 and a
  confirmed provider contribution of 490 on revenue of 700 and cost of 210.
- Edge cases include no data, missing weeks, one week, zero revenue, losses,
  refunds, unconfirmed provider costs, missing attribution, partial windows,
  year/leap boundaries and independence from the caller's Decimal context.
- API tests verify exact decimal strings, authentication, provider permission
  denial before reading, absence of provider identities in general output,
  explicit currency failure and response-schema compatibility.
- Streamlit AppTest checks the populated dashboard, three chart specifications,
  exact displayed metrics, empty state and existing login/import scaffolding.
  This is programmatic UI verification, not live browser screenshot testing.
- One 50,000-row pure-function benchmark completed in **0.056 seconds**, with
  exact revenue of 500.00 and 52 weekly periods. This does not measure network,
  database, container or complete page latency.

The 28 skipped tests include the earlier 24 integration cases and four new checks:
view column privacy, PostgreSQL Decimal/read-audit behavior, exclusion of deleted
uploads, and refusal of missing currency metadata. PostgreSQL and Docker are not
available here. Full database, migration and container acceptance remains pending.

## Assumptions and limits

No Section 12 stakeholder answer was supplied or invented. Access lists, approved
category/provider labels and cost-completeness declarations are empty by default.
All demonstration data is explicitly synthetic. Statistical definitions are
engineering conventions, displayed in the demo and returned by the API:

- Monday-start weeks and calendar months, inclusive date filters.
- Totals describe imported records; they do not prove complete accounting books.
- No-row periods are unknown. A period with imported expenses but no imported
  revenue has observed revenue zero; this is not a completeness certification.
- Averages use available observations in the trailing calendar window; gaps and
  partial windows are disclosed. Growth is omitted across gaps, trimmed periods
  and nonpositive prior denominators.
- Margin/category percentages require positive revenue. CV requires at least two
  eligible periods and a nonzero mean; it is reported as a unitless ratio.
- Provider contribution uses attributed expense records only after completeness
  is explicitly confirmed for the entire selected range; no overhead allocation
  or missing salary/benefit amounts are inferred.
- Category definitions apply as currently classified. This is not an SCD/history
  reconstruction of category changes.
- Unapproved category identities are grouped into Other fixed/variable expenses
  for general users. Provider labels and expenses require separate API access.
- Monetary API fields are decimal strings. Charts use safely bounded integer cents
  for presentation only; exact tables remain available for larger amounts.
- Requests are bounded to 250,000 rows and ten years; no silent truncation occurs.

The production custom frontend, staffing simulation, text-to-SQL and Phase 6
hardening remain outstanding. Stop here for confirmation before Phase 4.
