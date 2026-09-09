# Keep raw uploads out of durable storage

Status: Accepted implementation tradeoff

Decision: Bound the raw request body to 10 MiB in memory. Perform pluggable extraction and strict normalization off the ASGI event loop, then queue only dates, exact decimal text, approved type values and known internal IDs plus fixed rejection codes. Never persist the original filename, raw bytes or rejected cell contents. A file-level structural error is not queued.

Consequences: The UI submits through a background future; the durable worker owns catalog validation and fact persistence. HTTP acceptance latency includes preflight. There is no durable raw-file replay. This is not a PHI detector or a legal no-PHI determination. Unknown Section 12 scope still blocks real onboarding. Future stronger process isolation must be added without relaxing this boundary.
