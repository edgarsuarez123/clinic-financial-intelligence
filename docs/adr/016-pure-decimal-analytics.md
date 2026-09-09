# Pure Decimal analytics and missing-data semantics

Status: Accepted engineering definitions

Decision: Keep all financial calculations in app/analytics/calculations.py with standard-library dependencies only and a deterministic local Decimal context. Treat missing calendar periods as unknown. Use Monday-start weeks, calendar months, observed-window moving averages, positive-denominator growth/margins and population weekly CV. Surface definitions and sample counts.

Consequences: No statistics are calibrated from invented clinic history. These conventions are visible and replaceable. Numerical results remain Decimal until exact-string JSON serialization; no endpoint relies on UI arithmetic.
