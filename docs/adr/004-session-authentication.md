# Opaque revocable sessions

Status: Accepted as a reversible technical choice

Decision: Use Argon2id password hashes and 256-bit random bearer tokens. Store only token digests with UTC expiry; consult account and session active state each request. Logout soft-revokes the token. Default TTL is 30 minutes, configurable. Database-backed per-username attempt limits default to 5 per 900 seconds; successful logins also consume this limit. No signup or default account.

Consequences: This avoids signing-key management and permits immediate logout/account revocation. It is first-party session authentication, not an OAuth authorization server. Network-wide distributed-abuse protection and account recovery remain hardening work. The necessary anonymous login endpoint is an explicit interpretation of I8.2; no financial endpoint is anonymous.
