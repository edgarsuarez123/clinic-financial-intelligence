# 036 — Budget studio and persistent conversational analysis

Status: accepted by owner, 2026-09-10.

Replace the long budget form with Starting financials, Monthly plan, Scenarios and Compare views. Preserve existing saved inputs/results and revision guards. Soft deletion is recoverable; neither deletion nor restoration may overwrite a concurrent revision. An imported baseline is a snapshot, not a live link; baseline refresh requires explicit review. Costs and hires are additive only where marked as future changes.

Clarity conversations and result attachments belong in PostgreSQL, not browser storage. Every read and tool execution checks the current actor and compensation permission. A saved result cites the actual scenario revision, dates and currency. The LLM selects reviewed read tools and proposes a typed draft; it receives no SQL-write capability. Numeric outputs come from PostgreSQL or Decimal calculation functions. Narrative interpretation is labeled inference and must cite returned facts; it is not proof of causation. Applying a proposed plan is a separate explicit user action.

Keep the existing React/Vite/FastAPI/PostgreSQL architecture and deployment. No new cloud platform, public deployment or stakeholder assumptions are implied. Skill profile: authenticated desktop/broadband SPA, WCAG AA target, implementation owner coding agent; ongoing accessibility owner remains unassigned. Targets remain p75 LCP 2500ms, INP 200ms, CLS 0.1, Lighthouse accessibility 95/performance 90, initial JS 200 KiB gzip and route-specific 80 KiB. These are not measured results. Uploaded frontend helper/reference files are unavailable.

Statistical forecasts are a separate data-gated tool, evaluated against held-out chronological observations and simple benchmarks. Short/sparse histories must not produce invented probabilities. Scenario multipliers remain explicit assumptions, never confidence intervals. Cash on hand and legal payroll obligations are not inferred from revenue/expense records.

## Calculation contract

Driver revenue is the sum of each insurance/code row's units multiplied by its expected collected payment. It replaces existing amount-based revenue; explicitly incremental provider revenue is added separately. Scenario revenue, volume and payment multipliers multiply together. The clinic variable-cost percentage applies only to existing/driver revenue; each incremental group uses its own variable-cost assumption. Recorded fixed-cost rows must exclude any amounts the user separately models as variable costs.

A synthetic worked example, covered by a test: 800 units at 100 each gives revenue of 80,000. With fixed costs of 60,000 and additional variable costs of 5%, net is 16,000 and margin is 20%. Volume at 90% and payment at 95% gives revenue of 68,400 and net of 4,980. These are entered assumptions, not payment-rate or clinic benchmarks.

Monthly salary overrides are per person; benefits and effective payroll-tax percentages recalculate from that month's salary and headcount. Timing is by full plan/hire-relative months, without daily proration. Baseline comparisons use the stored whole-clinic snapshot. Provider-derived revenue inputs continue to resolve their explicitly selected historical dates on recalculation; Clarity identifies this refresh in a proposed draft so a changed import is not presented solely as the impact of an edited cost.

## Persistence and tool boundary

Migration 009 adds private conversations/turns and three aggregate read views. It leaves applied migrations unchanged. Budget deletion/restoration reuses the existing saved-budget storage. Autosave uses the existing optimistic revision contract with one active request, follow-on saves for intervening edits and an unchanged creation UUID on retry. Invalid inputs remain in the editor and stop saving until corrected; this is not offline storage.

Conversation generation reserves one turn in a short transaction. Retries use the same ID/input hash; an expired attempt receives a new token after six minutes (covering both 150-second Ollama stages). Only that token can complete the turn, and deletion of the parent prevents late resurrection. Threads are capped at 100 questions. Model context is bounded to recent messages and up to three attached plans; this is not unlimited conversational memory. Plan lists are paginated, and the model receives the first page of available plan names plus explicitly selected inputs. Queries remain restricted to reviewed aggregate shapes; unsupported custom filters/models/edits must refuse.

Facts, tables and cited plan revisions persist with each reply. Protect the thread before passing permission-sensitive plan inputs to a model, including failed attempts. A later permission revocation hides the protected thread. Soft deletion is not erasure, and saved answers are historical copies that do not change when source records change. Existing retention/erasure and customer-sharing policy questions remain unresolved.

## Forecast evaluation limits

Candidates are last observed month, trailing six-month mean and ordinary linear trend; seasonal-naive comparison is enabled only with sufficient earlier tuning history (64 months overall). Earlier rolling origins select a candidate, later origins estimate forecast errors. At least eight later errors are required per horizon. If the candidate does not improve one-month validation error over last-month revenue, use that benchmark and disclose the fallback. Reusing the validation set to reject the candidate means that report is not an untouched final performance estimate.

Ranges use empirical 10th/90th error percentiles, clipped to nonnegative revenue and widened to include the central estimate. They are not calibrated probability guarantees. The tool does not impute missing months or infer seasonal/causal business changes; 24 months supports only shorter horizons. Forecast output begins after the chosen historical end, not necessarily after today. Saved scenarios and this forecast remain separate until a user explicitly changes a plan. Live-data/model evaluation, including bias and forecast coverage, remains outstanding.
