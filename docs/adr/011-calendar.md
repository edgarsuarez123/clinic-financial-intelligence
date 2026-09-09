# Explicit date range and ISO calendar fields

Status: Accepted technical representation; clinic reporting calendar remains open

Decision: Provide an operator-command seed with required start/end dates. Store ISO week, ISO year and Monday week_start in addition to calendar month/quarter/year/day_of_week. No historical horizon is assumed or seeded automatically.

Consequences: Keeping ISO year prevents merging week 1 from distinct years. The reporting calendar and treatment of incomplete weeks are decisions for analytics; storing ISO fields does not assert the clinic uses ISO reporting periods.
