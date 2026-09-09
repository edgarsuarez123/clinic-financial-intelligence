# Phase 5 handoff — quantitative financial questions

Cumulative Phases 1–5, application version 0.5.0. Phase 6 has not started.

## Implemented

| Requirement | Implementation |
|---|---|
| F4.1 plain-language question | Authenticated UI/API with explicit date range and external-processing acknowledgment |
| F4.2 parameterized text-to-SQL | Model returns actual SQL; only exact reviewed catalog statements with matching bound dates execute |
| F4.3 read-only role | Dedicated clinic_query connection, SELECT-only read-view grants, role checks and read-only transaction |
| F4.4 grounded explanation | Results sent back to model; only valid returned row/metric references can supply explanatory values |
| F4.5 SQL and raw result | UI shows SQL, bound dates, exact result table, interpretation and snapshot metadata |
| F4.6 explicit refusal | Unsupported/low-confidence translation, unsafe SQL or ungrounded explanation returns “I can’t answer that reliably.” |
| F4.7 allowlist | Full registered statement allowlist constrains tables, statement types, functions and expressions |
| F4.8 repeated-question cache | User/scope/model/configuration/question/date/data-revision cache keys and configurable TTL |
| F4.9 clinic rate limit | PostgreSQL row-lock accounting shared across workers and users |
| N6.15 graceful LLM outage | Question requests fail cleanly; dashboards and budgets retain independent routes |
| N6.17 loading/latency | Explicit loading state and time expectation |
| N6.18 cost monitoring | Token usage, configured-price estimates, cache hits, unknown usage and incomplete-request counts |

Migration 005 adds aggregate query views, SELECT grants, data-revision invalidation, a cache, a rate counter and query-log usage fields. Migrations 001–004 remain unchanged. ADRs 024–027 explain scope and tradeoffs. `progress.md` summarizes every phase and architectural decision. `how-to-run.md` documents isolated environments, dummy-data workflows and the production handoff.

## Deliberate boundaries

This release supports six reviewed query shapes, not arbitrary SQL generation. Unsupported filters, forecasts, arbitrary joins and causal claims are refused. General questions cannot retrieve provider identifiers; provider mode requires both compensation access and explicit selection. Provider net is observed revenue minus recorded cost, not certified fully loaded margin.

The remote adapter supports a configured HTTPS chat-completions-compatible provider without a vendor SDK. Actual credentials, model choice, agreement/disclosure references and prices remain unconfigured. Real model semantic accuracy has not been evaluated. A self-reported confidence threshold is not a correctness proof.

Dev/test additionally supports a visibly labeled local deterministic adapter with six fixed prompts. It makes no external API calls; database execution still uses the read-only role. This adapter is rejected in production and staging.

## Validation

151 tests passed; 47 PostgreSQL-dependent tests skipped. Two existing dependency deprecation warnings remain. SQL parsing succeeded for migration 005 and all six catalog statements; Python compilation and Compose YAML parsing succeeded. Tests cover malicious/out-of-scope statements, parameter tampering, provider permissions, confidence refusal, result grounding, cache scope/revision changes, rate-limit behavior, token recording, HTTP adapter behavior, the question UI, environment isolation, demo-production rejection and the 52-row dummy-history parser.

The PostgreSQL tests include write/DDL denial even with READ WRITE explicitly selected, protected-table denial, runtime role rejection, catalog execution, revision invalidation and transactional cache/rate/usage auditing. They are included but not run here. Docker/Compose execution, live database migrations/durability and real LLM interoperability/accuracy are unverified in this environment. No production deployment or real financial-data transmission occurred.

## Next gate

Stop here pending Phase 6 confirmation. Hardening still needs TLS and encryption-at-rest deployment, tested automated backup/restore, export, agreed retention/deletion behavior, external audit retention, alerting and runbooks. The custom production frontend remains a separate pre-launch requirement. Resolve the outstanding clinic scope, access and cost-basis questions before any real data is onboarded.
