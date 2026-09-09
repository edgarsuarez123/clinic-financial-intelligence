# Soft deletion and permanent deletion are unresolved

Status: Open specification conflict

Decision: N6.14 requires soft deletion and never row removal. C5.7 requires a clinic-initiated deletion policy. Soft deletion leaves data recoverable and cannot by itself support a promise of permanent erasure. Preserve soft-delete markers and block physical fact/account/session deletion in this phase. Audit data remains append-only.

Consequences: Before Phase 6 export/deletion ships, obtain an approved policy separating operational soft deletion from end-of-contract erasure, audit retention, backup expiry and any exceptions. Do not silently reinterpret either requirement or claim an erasure capability.
