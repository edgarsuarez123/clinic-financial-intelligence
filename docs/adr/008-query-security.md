# Text-to-SQL boundary

Status: Accepted for Phase 5; not implemented

Decision: Retain text-to-SQL, never vector retrieval as the calculation engine. Provision a separate clinic_query login with no initial schema/table permissions and a read-only transaction default. Later add only approved read-only views/grants, parser-based SQL validation, parameter binding and resource limits.

Consequences: The current role is intentionally unusable for analytics. A read-only default is defense in depth and can be overridden by a client; permission grants are the actual boundary. Future cache keys must include data revision, access policy, model/prompt version and the exact question to avoid stale or cross-permission answers.


Phase 5 update: the boundary is now implemented. ADRs 024–026 describe the current grants, exact full-statement allowlist (superseding the planned free-form parser), bound parameters, cache and provider protocol.
