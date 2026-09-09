# ADR 029 — Optional local Ollama for synthetic development and testing

Accepted 2026-09-08 at the user's request. The existing deterministic demo remains available for predictable offline tests. `ollama` adds genuine model translation using native `/api/chat`, JSON output, nonstreaming responses and zero temperature. Usage comes from native token counts. Zero configured token price means no API charge, not free local compute.

Startup rejects this transport outside dev/test; configuration requires synthetic data, local endpoint allowlisting on port 11434, zero token prices and no cloud model tags. The optional Compose overlay runs a separate model server with a per-project model volume and no published port. No credentials or login to a cloud service are provided. Custom local servers must not forward prompts to cloud models.

The model only translates and selects returned cells. Existing catalog validation, read-only database credentials, permissions, cache, rate limits, logging and fail-closed explanations remain unchanged. Local HTTP is the explicit dev/test exception; the HTTPS external adapter still requires disclosure and DPA configuration. UI processing text reflects the selected transport.

The adapter disables environment HTTP proxies, follows no redirects, bounds output size and request duration, and rejects incomplete generations. Errors leave dashboards and saved budgets available. Local model quality and hardware latency require validation with the selected model; an adapter test is not an actual-model test.

Protocol reference: https://docs.ollama.com/api/chat (reviewed 2026-09-08).
