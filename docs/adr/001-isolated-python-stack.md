# Single-clinic Python stack

Status: Accepted from SRD

Decision: Each deployment uses the same Python/FastAPI codebase with its own PostgreSQL database and containers. Streamlit is reserved for subsequent UI phases. No tenant_id or logical multi-tenancy is introduced. Sites hosting is not used for this backend foundation because its Worker runtime would replace the explicitly required Python/PostgreSQL/Docker stack.

Consequences: No alternate frontend or infrastructure is substituted. A future tenant boundary remains a service/deployment concern.
