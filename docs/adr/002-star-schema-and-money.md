# Star schema and exact currency

Status: Accepted from SRD with precision implementation detail

Decision: Store financial facts separately from provider/category/date dimensions. Money uses PostgreSQL NUMERIC and Python Decimal. For transaction amounts, reject values with more than two fractional places using CHECK rather than NUMERIC(p,2), which can round an input before validation. Reject NaN and infinities. No currency conversion or sign interpretation is implemented.

Consequences: The transaction bound is 16 integer digits and 2 decimal places, an engineering storage bound, not a clinic financial assumption. Nullable provider_key preserves practice-level expenses. Category/type semantic validation belongs to ingestion before persistence; no ingestion exists yet.
