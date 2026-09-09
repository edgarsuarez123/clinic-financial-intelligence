# Exact financial API values and bounded chart rendering

Status: Accepted

Decision: Serialize every financial number as a decimal string or null, and define OpenAPI response models for the custom frontend. Perform no financial calculations in the chart library. For display only, round to cents with Decimal and pass integer cents below the browser exact-integer limit; format axes as currency and preserve exact displayed tables. Break line segments across missing raw data.

Consequences: Large amounts fall back to exact tables rather than lossy chart conversion. Moving-average chart points are presentation-rounded, while API averages preserve their Decimal precision. The browser still performs graphical coordinate/axis formatting; that is not the source of financial results.
