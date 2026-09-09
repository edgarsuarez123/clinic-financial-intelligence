# ADR 026 — Provider-independent interface and external-processing setup

Accepted in Phase 5. A small completion protocol separates the query service from vendor transport. The implemented remote adapter supports a configured HTTPS chat-completions-compatible endpoint with JSON-object responses. No vendor SDK is required. Other transports can implement the same protocol. Endpoint, provider/model identity, token prices and pricing currency are configuration; the API key is an environment secret and is not included in prompts, query logs or application logs.

Remote operation is disabled by default. Enabling requires explicit account permissions, provider settings, token prices and references to the clinic's written disclosure and executed DPA. Those references are operator attestations, not automated legal review or signed agreements. The user-facing form describes what leaves the clinic instance and requires acknowledgment before submitting. A checkbox does not replace C5.5/C5.6 agreements. No actual provider, agreement or financial-data transmission has been assumed or activated during this build.

Translation sends the question, selected dates and reviewed query catalog. Explanation sends the question, executed SQL/parameters and aggregate results. Provider identifiers and recorded attributed costs are included only in the explicitly authorized provider scope. Questions are retained in the clinic query log, so patient identifiers must not be entered. The no-PHI scope-change trigger still applies.

The adapter disallows HTTP redirects, bounds response size and time, requests no provider-side stored completion where supported, and treats transport/schema failures as unavailable. Provider retention terms must still be verified independently; a request flag is not a guarantee. Other modules do not depend on LLM availability.

Primary format reference: [chat completion API contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). Compatibility with a chosen vendor/model must be exercised before enabling it for real users.
