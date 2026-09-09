# PostgreSQL as the ingestion job queue

Status: Accepted Celery-equivalent for the design target

Decision: Use a normalized job table and a separate worker container. Lock one pending upload/job with FOR UPDATE SKIP LOCKED and hold the transaction through the full fact insert, summary update and audit write. Use a savepoint so a caught processing error records failure without partial facts. Connection death rolls back the outer transaction and releases the job for another worker.

Consequences: No Redis/Celery broker is needed at this volume. Lock-held processing keeps the visible state pending until terminal commit; the UI says queued or processing. Worker polling is bounded and shutdown-aware. Failed jobs require an explicit retry; retry preserves the normalized payload and mapping hash. Integration behavior must still be exercised against real PostgreSQL.
