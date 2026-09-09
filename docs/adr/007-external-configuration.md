# Keep business configuration unconfigured

Status: Accepted from SRD

Decision: Reserve clinic mappings, category taxonomy, cost assumptions, ramp-up parameters and financial access policy in an example configuration document with explicit null values. Runtime technical settings use environment variables validated at startup.

Consequences: Do not use plausible-looking sample compensation or ramp-up numbers as defaults. The example business configuration is not consumed by any unfinished module. Questions 1–8 remain open.
