# ADR 025 — Query credentials, revision cache, rate limits and usage

Accepted in Phase 5. Migration 005 grants `clinic_query` SELECT only on three designated aggregate/quality views and a data-revision counter. It receives no base-table, saved-budget, account, query-log or write grants. The query executor uses QUERY_DATABASE_URL, explicitly starts a repeatable-read/read-only transaction, checks the role identity and rejects role memberships or elevated privileges. Statement and lock timeouts bound execution. Prompt instructions are not the database security boundary.

The application role continues to write operational records, cache and audit entries through fixed parameterized SQL. It never executes model-selected analytics SQL using its credentials. Financial-query access requires both query and analytics allowlists. Provider queries additionally require the existing compensation permission plus explicit provider-data selection. Cost reporting has its own configured allowlist.

The cache key includes the exact question, date window, requesting user, provider scope, configuration, provider/model, catalog/prompt protocol version and committed financial-data revision. Statement triggers increment that revision for changes to facts, uploads and relevant dimensions. The executor checks the revision inside its transaction; changes during translation cause refusal/retry instead of mixing snapshots. Cached answers retain their original snapshot time, expire after a configurable TTL, and cannot cross users or permission scopes. Expired cache rows remain retained until the approved retention process is implemented.

A database row lock serializes clinic-wide rate accounting across processes. Cached requests count toward the request limit. Every accepted question receives a query-log record before translation; rate-limited questions are recorded too. API authorization/validation failures are audited by their applicable routes and do not cause an external call. Successful completions record usage before model-content validation, so rejected content still records reported token usage. Failed/indeterminate calls are marked unknown. Interrupted in-progress requests remain visible as incomplete.

Token costs are calculated in SQL from explicitly configured decimal prices; usage reports group by pricing currency. They report estimated known cost, unknown-usage calls and incomplete requests. This is not a provider invoice. Audits and financial responses fail closed on audit-write failure. Database administrators remain outside the application threat boundary; this is not protection from a compromised superuser.

Primary implementation references: [PostgreSQL privileges](https://www.postgresql.org/docs/17/ddl-priv.html), [read-only transactions](https://www.postgresql.org/docs/17/sql-set-transaction.html), and [Psycopg parameter binding](https://www.psycopg.org/psycopg3/docs/basic/params.html).


The validated SQL and bound dates are also committed to the query log with an execution audit before the financial SELECT. An audit failure prevents execution; a later process interruption does not erase which query was about to run.
