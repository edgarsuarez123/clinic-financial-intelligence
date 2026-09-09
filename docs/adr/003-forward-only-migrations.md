# Forward-only migrations and restricted runtime

Status: Accepted

Decision: Version SQL files in migrations/. Execute them as clinic_migrator inside one PostgreSQL transaction protected by a fixed advisory lock. Store SHA-256 checksums in migrations.applied. Reject altered/missing history or out-of-order insertion. No down migrations or ORM create_all. Provision clinic_app with only explicit authentication and audit-insert grants.

Consequences: The API does not receive migration credentials. Migration errors roll back the transaction. Future grants require new migration files. Cluster bootstrap credentials exist only on the local database service; production secret handling is a Phase 6 task.
