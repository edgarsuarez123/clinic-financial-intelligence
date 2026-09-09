# Refresh continuity and actuals-based scenarios

## Decision
React navigation uses URL fragments with browser history support. The expiring
bearer session is retained in sessionStorage for the tab and revalidated through
auth/me on refresh. Logout and API 401 clear it. This supersedes ADR 028's
memory-only session decision. Financial responses and budget drafts are not
persisted in browser storage. JavaScript can access this token, so XSS remains a
risk; the same-origin CSP remains required. HttpOnly cookies with CSRF protection
remain a production-hardening option.

Percentages are formatted to two decimal places at presentation boundaries.
Raw query results and calculations retain their original decimal precision.
Explanations are progressively disclosed instead of occupying the main screen.
Ask Clarity uses submission-time processing acknowledgment and an explicit scope
selector, with clinic-only scope by default. Server permissions are unchanged.

The baseline endpoint requires both simulation and general analytics access.
It averages recorded revenue and category costs across an explicitly selected
complete-month range. Missing months and partial months are rejected, not imputed.
Monthly averages become editable cent-rounded inputs in a new plan, including
existing payroll. Staff rows in that new plan start empty to avoid charging that
payroll twice. Future hires and costs are additions. Baseline costs assume
recurrence; users must remove one-time historical expenses before relying on them.
The source dates and method are saved in the existing assumption field, so saved
results do not silently change when more data is imported. Rebase explicitly to
use newer actuals. This is a run-rate scenario, not a fitted seasonal forecast.

Demo fixtures contain fictional employees, synthetic daily financial aggregates,
real insurer names and code identifiers, and invented payment/cost amounts.
They include no patient or encounter identifiers. They are never fee schedules,
tax advice, real staff records, or evidence of a payer contract.
