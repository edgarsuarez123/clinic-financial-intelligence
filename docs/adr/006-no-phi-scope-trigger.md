# No-PHI boundary and mandatory scope reconsideration

Status: Accepted design constraint; legal conclusion not asserted

Decision: Accept only the aggregate financial input scope in Section 5.1. If a clinic requests patient-identifier ingestion, or a feature associates records with identified individuals, the prior no-PHI determination is void. Stop that feature from shipping until the Section 5.3 compliance review and applicable safeguards and agreements are completed.

Consequences: This foundation exposes no upload endpoint. Phase 2 must define rejection before raw uploads, parser errors, temporary files, filenames or logs can retain patient information. Detection alone cannot establish a blanket legal exemption; stakeholder answer 8 is required before clinic ingestion.
