# General analytics and compensation access are separate

Status: Accepted provisional least-privilege design

Decision: Expose retained completed-upload facts through two SELECT-only views. The general view omits provider identifiers. The API requires an explicit analytics account allowlist and an additional subset allowlist for provider access. Mask non-approved category identities into fixed/variable groups. Audit every repository read.

Consequences: The shared runtime role may read both views; application authorization is the HTTP user boundary. These grants do not authorize a clinic user or expose base-table SELECT. General aggregates are not a statistical anti-inference mechanism. Current category classification applies to historical facts; deleted uploads/facts are excluded.
