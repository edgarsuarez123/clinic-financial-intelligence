# ADR 030 — Dev host port and authentication row-lock grant

Accepted 2026-09-08. The user reported Docker Desktop occupying host port 8000 and PostgreSQL rejecting session creation's `SELECT ... FOR UPDATE`.

New dev environments use `API_PORT=8010`; the container still listens on 8000. Test/staging/production retain isolated defaults; web ports are 3000/3001/3002/3003. Existing environment files are not regenerated or credentials overwritten. The shared Compose fallback is 8010.

Forward-only migration 006 grants `UPDATE ON core.app_user TO clinic_app`, as requested, because PostgreSQL requires UPDATE privilege for row-locking SELECT. Foundation migration 001 is not modified, preserving migration checksums. This expands runtime privilege on the account table; keeping the lock protects against concurrent account deactivation. No account mutation HTTP endpoint is introduced. A narrower privilege architecture can be considered in hardening.

The existing real-auth lifecycle integration test exercises login, session resolution and logout against a migrated database. Running it and applying the migration require PostgreSQL/Docker, unavailable in this build workspace. The migration file is included, not claimed as applied on the user's machine.
