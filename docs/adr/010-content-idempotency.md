# Upload-level content hash uniqueness

Status: Accepted from SRD

Decision: A global unique SHA-256 content_hash in each isolated clinic database enforces one upload identity even across simultaneous inserts. The uniqueness remains after soft deletion. Source_upload_id is required for every transaction.

Consequences: This is a schema prerequisite, not completed ingestion idempotency. Phase 2 needs atomic processing/retry semantics and the required identical-upload test. Hashes do not deduplicate overlapping, reformatted or reordered exports; stakeholder transaction identifiers are needed before broader deduplication.
