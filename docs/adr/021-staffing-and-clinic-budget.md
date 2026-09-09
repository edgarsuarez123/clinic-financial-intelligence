# ADR 021 — Decimal staffing and whole-clinic budget simulation

Accepted for Phase 4. The user expanded staffing simulation to configurable employee counts, employer payroll taxes, rent, utilities, software and new clinic costs.

Use pure Decimal functions for both individual hire contribution and a whole-clinic plan. The authenticated `/api/v1/simulations/clinic` endpoint handles both: a single incremental staff group and explicit zero existing revenue represents an individual hire. Simulation results are computed on demand, without persisting plans or changing financial facts. Identical inputs and historical snapshot produce identical results. No new migration is necessary; migrations 001–003 remain unchanged.

All pay and revenue inputs are per employee. Headcount multiplies them. Benefits and employer payroll taxes are separately entered effective percentages of salary; no jurisdiction, wage cap, bundled-cost policy or real clinic rate is assumed. Clinic monthly and one-time costs have explicit start/end months. Historical expenses are not automatically added to the plan. Existing staff revenue is counted in the clinic baseline only; incremental groups explicitly add revenue.

Annual costs divide by 12 in a 50-digit Decimal context. Full plan-relative monthly periods have no daily proration. One-time costs occur at their start period; other activity closes monthly. Break-even means the first nonnegative cumulative close; also return sustained break-even within the horizon, because an early crossing can reverse. Deficits do not model every intra-month cash need. Monetary JSON uses decimal strings; input JSON floats are rejected.

Each of three named scenarios specifies its own revenue and recurring-cost multipliers and piecewise ramp. The shared ramp applies relative to each incremental group's start, not existing clinic revenue. Curves remain explicitly assumed; hiring-history calibration is unavailable. All inputs and timing conventions accompany every result and are shown adjacent in the temporary UI. Monte Carlo remains a stretch goal.


Update: ADR 023 supersedes this record’s session-only storage decision with durable named budgets and saved result snapshots.
