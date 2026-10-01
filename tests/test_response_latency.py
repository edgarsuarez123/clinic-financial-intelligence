"""
Response Latency Test Suite
============================
Measures end-to-end latency of the server-side query pipeline:
  validate_sql → render_explanation

This covers all server-side work *excluding* the LLM call and database
query — which dominate real-world latency and must be measured against
live infrastructure. See the note at the bottom of this file.

Metric: average latency and p95 (worst-case) latency in milliseconds.
Typical targets: avg < 5 ms, p95 < 15 ms for the validation+render layer.

Run:  pytest tests/test_response_latency.py -v -s
"""

import statistics
import time
from decimal import Decimal as D
from datetime import date
from uuid import uuid4

import pytest

from app.query.catalog import CATALOG, validate_sql, render_explanation
from app.query.schemas import Fact

# Number of full pipeline passes to time
N_RUNS = 30

START = date(2026, 1, 1)
END = date(2026, 3, 31)
_PARAMS = {'start': '2026-01-01', 'end': '2026-03-31'}


# ── Synthetic result sets ─────────────────────────────────────────────────────

_SUMMARY_ROWS = [
    {'currency': 'USD', 'revenue': D('58420.00'), 'expense': D('31200.00'),
     'net': D('27220.00'), 'margin_pct': D('46.60')}
]

_MONTHLY_ROWS = [
    {'year': 2026, 'month': m, 'currency': 'USD',
     'revenue': D(str(18000 + m * 200) + '.00'),
     'expense': D(str(10000 + m * 100) + '.00'),
     'net': D(str(8000 + m * 100) + '.00'),
     'margin_pct': D('44.44'),
     'revenue_growth_pct': D('2.00') if m > 1 else None}
    for m in range(1, 4)
]

_WEEKLY_ROWS = [
    {'week_start': date(2026, 1, 5 + i * 7), 'currency': 'USD',
     'revenue': D(str(13500 + i * 250) + '.00'),
     'expense': D(str(7200 + i * 80) + '.00'),
     'net': D(str(6300 + i * 170) + '.00'),
     'margin_pct': D('46.67')}
    for i in range(12)
]

_COST_ROWS = [
    {'currency': 'USD', 'fixed_cost': D('21000.00'), 'variable_cost': D('10200.00'),
     'fixed_cost_pct': D('67.31'), 'variable_cost_pct': D('32.69')}
]

_VOLATILITY_ROWS = [
    {'currency': 'USD', 'observed_weeks': 12, 'revenue_cv': D('8.32'),
     'expense_cv': D('4.17')}
]

_PROVIDERS_ROWS = [
    {'provider_key': str(uuid4()), 'currency': 'USD',
     'revenue': D('29000.00'), 'recorded_cost': D('18000.00'),
     'observed_net': D('11000.00')},
    {'provider_key': str(uuid4()), 'currency': 'USD',
     'revenue': D('22000.00'), 'recorded_cost': D('15000.00'),
     'observed_net': D('7000.00')},
]

# Pipeline test cases: (key, rows, facts)
_PIPELINE_CASES = [
    ('summary',        _SUMMARY_ROWS,    [Fact(row=0, column='revenue'),
                                          Fact(row=0, column='net')]),
    ('monthly',        _MONTHLY_ROWS,    [Fact(row=0, column='revenue'),
                                          Fact(row=2, column='revenue_growth_pct')]),
    ('weekly',         _WEEKLY_ROWS,     [Fact(row=0, column='revenue'),
                                          Fact(row=11, column='margin_pct')]),
    ('cost_breakdown', _COST_ROWS,       [Fact(row=0, column='fixed_cost'),
                                          Fact(row=0, column='fixed_cost_pct')]),
    ('volatility',     _VOLATILITY_ROWS, [Fact(row=0, column='revenue_cv')]),
    ('providers',      _PROVIDERS_ROWS,  [Fact(row=0, column='observed_net'),
                                          Fact(row=1, column='revenue')]),
]


# ── Latency measurement ───────────────────────────────────────────────────────

def _time_pipeline(key: str, rows: list[dict], facts: list[Fact]) -> float:
    """
    Time one full validate_sql + render_explanation pass.
    Returns elapsed time in milliseconds.
    """
    sql = CATALOG[key].sql
    provider_access = key == 'providers'

    t0 = time.perf_counter()
    validate_sql(key, sql, _PARAMS, START, END, provider_access)
    render_explanation(facts, CATALOG[key], rows)
    t1 = time.perf_counter()

    return (t1 - t0) * 1000  # ms


def test_response_latency():
    """
    Runs N_RUNS iterations of the validation+rendering pipeline and reports
    average and p95 latency.

    Scope: server-side only (validate_sql + render_explanation).
    LLM and database latency are NOT measured here — see note below.
    """
    latencies_ms: list[float] = []

    # Cycle through all query shapes across N_RUNS iterations
    for i in range(N_RUNS):
        key, rows, facts = _PIPELINE_CASES[i % len(_PIPELINE_CASES)]
        elapsed = _time_pipeline(key, rows, facts)
        latencies_ms.append(elapsed)

    avg_ms = statistics.mean(latencies_ms)
    p95_ms = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
    p50_ms = statistics.median(latencies_ms)
    min_ms = min(latencies_ms)
    max_ms = max(latencies_ms)

    print(f"\n{'='*60}")
    print(f"RESPONSE LATENCY REPORT (server-side pipeline only)")
    print(f"{'='*60}")
    print(f"Iterations:   {N_RUNS}")
    print(f"Query shapes: {len(_PIPELINE_CASES)} (cycled)")
    print()
    print(f"Average:      {avg_ms:.2f} ms")
    print(f"Median (p50): {p50_ms:.2f} ms")
    print(f"p95:          {p95_ms:.2f} ms   ← worst-case for UX")
    print(f"Min:          {min_ms:.2f} ms")
    print(f"Max:          {max_ms:.2f} ms")
    print()
    print(f"NOTE: LLM call and database query latency are NOT included.")
    print(f"      For full end-to-end latency, see the integration note below.")

    # Hard ceiling: if validate_sql + render_explanation take > 100 ms,
    # something is fundamentally wrong (CPU-bound pathology).
    assert avg_ms < 100, (
        f"Server-side pipeline average {avg_ms:.2f} ms exceeds 100 ms ceiling. "
        f"Investigate validate_sql or render_explanation for unexpected blocking."
    )
    assert p95_ms < 500, (
        f"Server-side pipeline p95 {p95_ms:.2f} ms exceeds 500 ms ceiling."
    )


@pytest.mark.parametrize('key,rows,facts', _PIPELINE_CASES,
                         ids=[c[0] for c in _PIPELINE_CASES])
def test_single_pipeline_pass_completes(key, rows, facts):
    """Each query shape must complete a validate+render pass without error."""
    elapsed = _time_pipeline(key, rows, facts)
    assert elapsed >= 0  # trivially true; ensures no exception was raised


def test_latency_distribution_is_stable():
    """
    Runs 30 passes and checks that latency does not have extreme outliers
    (p95 < 10x median), indicating no intermittent blocking.
    """
    latencies = []
    for i in range(30):
        key, rows, facts = _PIPELINE_CASES[i % len(_PIPELINE_CASES)]
        latencies.append(_time_pipeline(key, rows, facts))

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]

    if p50 > 0:
        ratio = p95 / p50
        print(f"\nLatency stability: p95/p50 ratio = {ratio:.1f}x (target: < 10x)")
        assert ratio < 10, (
            f"p95/p50 ratio {ratio:.1f}x indicates unstable latency. "
            f"p50={p50:.2f} ms, p95={p95:.2f} ms"
        )


"""
NOTE — Measuring full end-to-end latency (including LLM + database)
=====================================================================
This test file measures only the server-side pipeline overhead
(validate_sql + render_explanation).  Real user-facing latency includes:

  1. LLM translation call   — dominant factor; typically 2–30 s depending
                              on provider, model, and question complexity.
  2. Database query         — typically 5–200 ms depending on data volume
                              and whether results are cached.
  3. LLM explanation call   — typically 0.5–5 s.
  4. Network round-trip     — depends on deployment topology.

To measure true end-to-end latency:

  1. Start the full stack:   docker compose up
  2. Run against a live API with an actual LLM provider configured.
  3. Time 20–30 real requests using a script like:

     import time, requests, statistics
     latencies = []
     for _ in range(30):
         t0 = time.perf_counter()
         requests.post('http://localhost:8010/api/v1/questions',
                       json={'question': 'What is total revenue?',
                             'start': '2026-01-01', 'end': '2026-03-31',
                             'acknowledge_external_processing': True},
                       headers={'Authorization': 'Bearer <token>'})
         latencies.append((time.perf_counter() - t0) * 1000)
     print(f"avg={statistics.mean(latencies):.0f} ms  "
           f"p95={sorted(latencies)[int(len(latencies)*0.95)]:.0f} ms")

  Report: average latency and p95 latency from this script.
"""
