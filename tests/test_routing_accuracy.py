"""
Query-Routing Accuracy Test Suite
===================================
Verifies that the catalog validation layer correctly:
  1. Accepts valid question → catalog-key mappings  (correct routing rate)
  2. Refuses genuinely out-of-scope model outputs    (correct refusal rate)
  3. Does not wrongly block in-scope questions       (false refusal rate)

How this works
--------------
validate_sql(key, sql, model_params, user_start, user_end, provider_access)
is the actual routing gate. It checks:
  - key exists in the catalog
  - sql exactly matches CATALOG[key].sql (character for character)
  - model_params match user-selected dates
  - provider_access matches the query's requirements

We simulate a labeled set of model outputs (what the LLM would return)
paired with user-selected dates (from the Question) and verify whether
the validation layer accepts or rejects each case as expected.

Three metrics:
  correct_routing_rate  — valid routes accepted / total in-scope cases
  correct_refusal_rate  — invalid routes refused / total out-of-scope cases
  false_refusal_rate    — valid routes blocked / total in-scope cases
                          (caused by the model making a routing error, not
                          a system bug — but costs the user a missed answer)

Run:  pytest tests/test_routing_accuracy.py -v -s
"""

from datetime import date

import pytest

from app.query.catalog import CATALOG, Unreliable, validate_sql

# User-selected dates for the baseline test window
USER_START = date(2026, 1, 1)
USER_END = date(2026, 3, 31)
_Q1_PARAMS = {'start': '2026-01-01', 'end': '2026-03-31'}


# ── Helper ────────────────────────────────────────────────────────────────────

def _route(key: str, sql: str, model_params: dict,
           provider_access: bool = False,
           user_start: date = USER_START,
           user_end: date = USER_END):
    """Call validate_sql with explicit user-selected dates vs. model output."""
    return validate_sql(key, sql, model_params, user_start, user_end, provider_access)


# ── LABELED TEST CASES ────────────────────────────────────────────────────────
#
# Tuple structure:
#   (description, key, sql, model_params, provider_access, user_start, user_end)
#
# For the correct routing cases the model returns exactly the right key + SQL
# and matching date params.  For refusal cases the model output has something
# wrong and validate_sql is expected to raise.

# ── In-scope: model returns correct output → must be accepted ─────────────────

CORRECT_ROUTE_CASES = [
    # All six catalog shapes with Q1 2026
    ('Revenue summary',
     'summary', CATALOG['summary'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Monthly revenue trend',
     'monthly', CATALOG['monthly'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Weekly revenue trend',
     'weekly', CATALOG['weekly'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Fixed vs variable cost breakdown',
     'cost_breakdown', CATALOG['cost_breakdown'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Weekly revenue volatility',
     'volatility', CATALOG['volatility'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Provider totals (with access)',
     'providers', CATALOG['providers'].sql, _Q1_PARAMS, True, USER_START, USER_END),
    # Same six shapes with a different (valid) date range
    ('Summary — Feb only',
     'summary', CATALOG['summary'].sql,
     {'start': '2026-02-01', 'end': '2026-02-28'}, False,
     date(2026, 2, 1), date(2026, 2, 28)),
    ('Monthly — full year',
     'monthly', CATALOG['monthly'].sql,
     {'start': '2026-01-01', 'end': '2026-12-31'}, False,
     date(2026, 1, 1), date(2026, 12, 31)),
    ('Weekly — single week',
     'weekly', CATALOG['weekly'].sql,
     {'start': '2026-03-02', 'end': '2026-03-08'}, False,
     date(2026, 3, 2), date(2026, 3, 8)),
    ('Cost breakdown — Q4 2025',
     'cost_breakdown', CATALOG['cost_breakdown'].sql,
     {'start': '2025-10-01', 'end': '2025-12-31'}, False,
     date(2025, 10, 1), date(2025, 12, 31)),
    ('Volatility — half year',
     'volatility', CATALOG['volatility'].sql,
     {'start': '2026-01-01', 'end': '2026-06-30'}, False,
     date(2026, 1, 1), date(2026, 6, 30)),
    ('Providers — full year',
     'providers', CATALOG['providers'].sql,
     {'start': '2026-01-01', 'end': '2026-12-31'}, True,
     date(2026, 1, 1), date(2026, 12, 31)),
    # Prior year
    ('Summary — full 2025',
     'summary', CATALOG['summary'].sql,
     {'start': '2025-01-01', 'end': '2025-12-31'}, False,
     date(2025, 1, 1), date(2025, 12, 31)),
    ('Monthly — Q3 2025',
     'monthly', CATALOG['monthly'].sql,
     {'start': '2025-07-01', 'end': '2025-09-30'}, False,
     date(2025, 7, 1), date(2025, 9, 30)),
    ('Weekly — Q2 2026',
     'weekly', CATALOG['weekly'].sql,
     {'start': '2026-04-01', 'end': '2026-06-30'}, False,
     date(2026, 4, 1), date(2026, 6, 30)),
]

# ── Out-of-scope: model returns bad output → must raise ───────────────────────

REFUSAL_CASES = [
    # Unknown / empty key
    ('Unknown catalog key',
     'total_revenue', CATALOG['summary'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Empty string key',
     '', CATALOG['summary'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    # SQL does not match registered statement (even minor deviations)
    ('SQL with trailing space',
     'summary', CATALOG['summary'].sql + ' ', _Q1_PARAMS, False, USER_START, USER_END),
    ('SQL with UNION injection',
     'summary', CATALOG['summary'].sql + ' UNION SELECT 1,2,3,4,5',
     _Q1_PARAMS, False, USER_START, USER_END),
    ('SQL swapped to different valid key',
     'summary', CATALOG['monthly'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('SQL with appended DROP TABLE',
     'weekly', CATALOG['weekly'].sql + '; DROP TABLE analytics.transactions',
     _Q1_PARAMS, False, USER_START, USER_END),
    ('SQL with stacked DELETE',
     'cost_breakdown',
     CATALOG['cost_breakdown'].sql + '; DELETE FROM analytics.transactions',
     _Q1_PARAMS, False, USER_START, USER_END),
    ('SQL with SET ROLE escalation',
     'summary', 'SET ROLE clinic_migrator; ' + CATALOG['summary'].sql,
     _Q1_PARAMS, False, USER_START, USER_END),
    ('Arbitrary SELECT not in catalog',
     'summary', 'SELECT * FROM analytics.transactions WHERE 1=1',
     _Q1_PARAMS, False, USER_START, USER_END),
    ('CTE with mutation',
     'summary',
     'WITH d AS (DELETE FROM analytics.transactions RETURNING *) SELECT * FROM d',
     _Q1_PARAMS, False, USER_START, USER_END),
    # Model changes the date parameters (user selected Q1, model returns different dates)
    ('Model shifts start date back one year',
     'summary', CATALOG['summary'].sql,
     {'start': '2025-01-01', 'end': '2026-03-31'},
     False, USER_START, USER_END),
    ('Model extends end date',
     'summary', CATALOG['summary'].sql,
     {'start': '2026-01-01', 'end': '2026-12-31'},
     False, USER_START, USER_END),
    ('Model swaps start and end',
     'summary', CATALOG['summary'].sql,
     {'start': '2026-03-31', 'end': '2026-01-01'},
     False, USER_START, USER_END),
    ('Model omits start parameter',
     'monthly', CATALOG['monthly'].sql,
     {'end': '2026-03-31'}, False, USER_START, USER_END),
    ('Model injects extra parameter',
     'monthly', CATALOG['monthly'].sql,
     {'start': '2026-01-01', 'end': '2026-03-31', 'role': 'admin'},
     False, USER_START, USER_END),
    # Provider access mismatch
    ('Provider query without access flag',
     'providers', CATALOG['providers'].sql, _Q1_PARAMS, False, USER_START, USER_END),
]

# ── False-refusal simulation ───────────────────────────────────────────────────
# These are valid in-scope questions where the model makes a routing mistake.
# validate_sql correctly rejects the bad model output — but from the user's
# perspective the question went unanswered (a false refusal).

FALSE_REFUSAL_CASES = [
    ('Valid revenue Q but model returns wrong key',
     'monthly', CATALOG['monthly'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Valid weekly Q but model returns summary SQL for weekly key',
     'weekly', CATALOG['summary'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Valid cost Q but model mutated one column name',
     'cost_breakdown',
     CATALOG['cost_breakdown'].sql.replace('fixed_cost', 'fixed_cost_total'),
     _Q1_PARAMS, False, USER_START, USER_END),
    ('Valid provider Q but model forgot to set provider_access',
     'providers', CATALOG['providers'].sql, _Q1_PARAMS, False, USER_START, USER_END),
    ('Valid volatility Q but model changed end date by one day',
     'volatility', CATALOG['volatility'].sql,
     {'start': '2026-01-01', 'end': '2026-03-30'},
     False, USER_START, USER_END),
]


# ── Main routing accuracy report ──────────────────────────────────────────────

def test_routing_accuracy():
    """
    Runs all labeled cases through validate_sql and reports three metrics.

    correct_routing_rate: how often valid model output is accepted
    correct_refusal_rate: how often invalid output is rejected
    false_refusal_rate:   how often a valid question is blocked due to model error
    """
    # --- In-scope routes ---
    route_correct = 0
    route_failures = []
    for desc, key, sql, params, pa, us, ue in CORRECT_ROUTE_CASES:
        try:
            _route(key, sql, params, pa, us, ue)
            route_correct += 1
        except Exception as exc:
            route_failures.append((desc, str(exc)))

    # --- Refusals ---
    refusal_correct = 0
    refusal_failures = []
    for desc, key, sql, params, pa, us, ue in REFUSAL_CASES:
        try:
            _route(key, sql, params, pa, us, ue)
            refusal_failures.append((desc, 'NOT refused — should have raised'))
        except Exception:
            refusal_correct += 1

    # --- False refusals ---
    false_refusal_count = 0
    for desc, key, sql, params, pa, us, ue in FALSE_REFUSAL_CASES:
        try:
            _route(key, sql, params, pa, us, ue)
        except Exception:
            false_refusal_count += 1  # model error → user gets refused

    n_in = len(CORRECT_ROUTE_CASES)
    n_out = len(REFUSAL_CASES)
    n_fr = len(FALSE_REFUSAL_CASES)

    correct_routing_pct = route_correct / n_in * 100 if n_in else 0.0
    correct_refusal_pct = refusal_correct / n_out * 100 if n_out else 0.0
    false_refusal_pct = false_refusal_count / n_fr * 100 if n_fr else 0.0

    print(f"\n{'='*60}")
    print(f"QUERY-ROUTING ACCURACY REPORT")
    print(f"{'='*60}")
    print(f"In-scope cases:          {n_in}")
    print(f"Out-of-scope cases:      {n_out}")
    print(f"False-refusal cases:     {n_fr}")
    print()
    print(f"Correct routing rate:    {route_correct}/{n_in} "
          f"({correct_routing_pct:.1f}%)")
    print(f"Correct refusal rate:    {refusal_correct}/{n_out} "
          f"({correct_refusal_pct:.1f}%)")
    print(f"False refusal rate:      {false_refusal_count}/{n_fr} "
          f"({false_refusal_pct:.1f}%)  ← watch this one")

    if route_failures:
        print(f"\nRouting failures (should have passed):")
        for d, e in route_failures:
            print(f"  FAIL: {d!r} → {e}")

    if refusal_failures:
        print(f"\nRefusal failures (should have been blocked):")
        for d, e in refusal_failures:
            print(f"  FAIL: {d!r} → {e}")

    assert not route_failures, (
        f"{len(route_failures)} in-scope cases were incorrectly rejected:\n"
        + '\n'.join(f"  {d}: {e}" for d, e in route_failures)
    )
    assert not refusal_failures, (
        f"{len(refusal_failures)} out-of-scope cases were NOT rejected:\n"
        + '\n'.join(f"  {d}: {e}" for d, e in refusal_failures)
    )


# ── Parametrized individual tests ─────────────────────────────────────────────

@pytest.mark.parametrize('desc,key,sql,params,pa,us,ue', CORRECT_ROUTE_CASES,
                         ids=[c[0] for c in CORRECT_ROUTE_CASES])
def test_valid_route_accepted(desc, key, sql, params, pa, us, ue):
    """Every in-scope model output with correct SQL must be accepted."""
    query, bound = _route(key, sql, params, pa, us, ue)
    assert query.key == key


@pytest.mark.parametrize('desc,key,sql,params,pa,us,ue', REFUSAL_CASES,
                         ids=[c[0] for c in REFUSAL_CASES])
def test_invalid_route_refused(desc, key, sql, params, pa, us, ue):
    """Every invalid model output must be rejected (raise an exception)."""
    with pytest.raises(Exception):
        _route(key, sql, params, pa, us, ue)
