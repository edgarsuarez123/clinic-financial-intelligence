# Separate audit and application records

Status: Accepted from SRD

Decision: Application logs emit allowlisted JSON metadata to stdout; request payloads, tokens, question strings and database errors are omitted. Audit events are written to audit.audit_log in PostgreSQL. Runtime can insert but cannot read, update, delete or truncate it. Triggers reject mutation and truncation even for ordinary owner-issued SQL. Authenticated route audit failure blocks a successful response.

Consequences: Audit retention and external archival must be established in Phase 6. A schema is not a separate failure domain or immutable external archive. Database administrators can disable triggers; this is append-only under normal database privileges, not protection against a compromised superuser.
