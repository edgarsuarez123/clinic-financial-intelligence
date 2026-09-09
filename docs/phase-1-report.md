# Phase 1 handoff

Author of source SRD: Edgar J. Suárez Colón. Build scope: Phase 1 only.

## What was built

| Phase 1 requirement | Deliverable |
|---|---|
| PostgreSQL star schema | migrations/001_foundation.sql |
| Forward-only migrations | app/migrate.py; locked transaction and checksums |
| Authentication | app/security.py, app/store.py, app/main.py, app/bootstrap.py |
| Docker | Dockerfile, compose.yaml, infra/init-db.sh |
| Structured application logging | app/logging_config.py; JSON stdout |
| Separate append-only audit records | audit.audit_log; grants and mutation triggers |
| Versioned REST skeleton | /api/v1/auth/*, /api/v1/health, authenticated OpenAPI |
| Precomputed date dimension | app/seed_dates.py with explicit range |
| Configuration and architecture records | config/clinic.example.json; docs/adr/* |

## Validation

Executed in this workspace:

- Python API/security/date unit suite: **27 passed, 18 integration tests skipped** (2.62 seconds). Two dependency deprecation warnings were emitted by the test client.
- Python compilation, shell syntax, and all three YAML configuration parses passed.
- PostgreSQL migration syntax parse using pglast 8.4: **32 SQL statements parsed**. This is syntax validation, not database execution.

Not executed here:

- PostgreSQL integration tests: this workspace has no running PostgreSQL server.
- Docker image build and Compose startup: Docker is unavailable here.
- GitHub Actions: the workflow is supplied for execution after repository setup.

The integration suite checks migration replay/checksum rejection, exact decimal
round-trip, invalid precision/nonfinite amounts, upload hash uniqueness, required
provenance, soft deletes, privilege denials, audit append-only enforcement,
real database authentication/logout and shared login throttling. A skipped test
is not a pass. Full Phase 1 acceptance remains pending these integration and
container gates. Unique upload hashes do not complete the Phase 2 idempotency test.

## Assumptions and limits

Only technical choices were made: Python 3.12, PostgreSQL 17 for Docker, opaque
sessions, configurable 30-minute expiry and login throttling, explicit schema
names, and ISO date representation. All are recorded in ADRs. No Section 12
stakeholder answers were invented. The no-PHI boundary is a design constraint,
not a legal determination produced by the application.

The runtime account has no financial grants. There is no approved financial RBAC
policy yet, no real clinic account or data, no Streamlit screen, and no Phase 2–6
functionality. TLS, encrypted volumes, tested backups/restore, production staging,
retention, monitoring and operations runbooks remain Phase 6 deliverables.

## Phase gate

Stop here as requested. Obtain confirmation before Phase 2. Resolve billing export
format, patient-identifier presence and authorized access before implementing real
clinic ingestion. Review docs/open-questions.md for the remaining stakeholder inputs.
