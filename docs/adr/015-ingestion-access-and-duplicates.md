# Explicit ingestion access and immutable upload identity

Status: Accepted provisional minimum access

Decision: Default ingestion configuration is disabled. Enabling requires a declared mode, a no-PHI scope confirmation, explicit account UUIDs and validated profiles. Only the originating uploader can read/retry a summary. Duplicate bytes under a changed mapping, another uploader or a deleted upload produce a conflict; they cannot bypass global hash uniqueness.

Consequences: This is a least-privilege implementation choice, not a stakeholder role assignment. Future compensation RBAC remains unresolved. Distinct bytes may overlap in real-world transactions; do not claim transaction-level cross-file deduplication. A profile hash and normalized IDs preserve mapping interpretation; catalog active state is checked before insertion.
