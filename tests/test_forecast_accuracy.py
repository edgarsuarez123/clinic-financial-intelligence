"""
Forecast Accuracy vs. Baseline Test Suite
==========================================
Verifies that the forecasting module's chosen method actually beats
the naive baseline (last_month) on synthetic time series with known
structure. Uses the same rolling-origin backtesting mechanism that
production forecasts use.

Metric: validation_mae of chosen method vs benchmark_mae of naive
baseline, expressed as percentage improvement.

Run:  pytest tests/test_forecast_accuracy.py -v -s

Note: this tests the forecasting engine against synthetic data.
To measure accuracy on real clinic data, supply live history rows.
"""

from decimal import Decimal as D
from datetime import date

import pytest

from app.simulation.forecast import forecast_months


# ── Synthetic time series builders ───────────────────────────────────────────

def _rows(amounts: list[str], start_year: int = 2023, start_month: int = 1) -> list[dict]:
    """Convert a list of monthly revenue strings to forecast_months input format."""
    rows = []
    year, month = start_year, start_month
    for amount in amounts:
        rows.append({'period': date(year, month, 1), 'revenue': D(amount)})
        month += 1
        if month > 12:
            month = 1
            year += 1
    return rows


def _pct_improvement(mae_method: D, mae_naive: D) -> float:
    """Return % improvement of method over naive baseline (positive = better)."""
    if mae_naive == 0:
        return 0.0
    return float((mae_naive - mae_method) / mae_naive * 100)


# ── Time series fixtures ──────────────────────────────────────────────────────

# 1. Linear upward trend: revenue increases ~$500/month
TREND_UP = _rows([str(5000 + i * 500) + '.00' for i in range(30)])

# 2. Linear downward trend: revenue decreases ~$300/month
TREND_DOWN = _rows([str(max(1000, 20000 - i * 300)) + '.00' for i in range(30)])

# 3. Flat series: same revenue every month (naive == any method)
FLAT = _rows(['8000.00'] * 30)

# 4. Seasonal: revenue cycles annually (higher Q4, lower Q1)
_SEASONAL_PATTERN = [6000, 6200, 6500, 7000, 7200, 7500,
                     8000, 8500, 9000, 10000, 11000, 9000]
SEASONAL = _rows([str(_SEASONAL_PATTERN[i % 12]) + '.00' for i in range(36)])

# 5. Volatile but mean-reverting: fluctuates around $7000
_BASE = 7000
VOLATILE = _rows([
    str(_BASE + 200 * (1 if i % 3 == 0 else -1 if i % 3 == 1 else 0)) + '.00'
    for i in range(30)
])

# 6. Minimum valid length (exactly 24 months)
MINIMUM_HISTORY = _rows(['5000.00'] * 12 + ['5500.00'] * 12)


# ── Accuracy tests ────────────────────────────────────────────────────────────

def _run_and_report(series_name: str, rows: list[dict], horizon: int = 6) -> dict:
    """Run forecast_months and return result with improvement metric."""
    result = forecast_months(rows, horizon=horizon)
    improvement = _pct_improvement(result['validation_mae'], result['benchmark_mae'])
    print(f"  [{series_name}]")
    print(f"    method:          {result['method']}")
    print(f"    history_months:  {result['history_months']}")
    print(f"    validation_mae:  {result['validation_mae']}")
    print(f"    benchmark_mae:   {result['benchmark_mae']}")
    print(f"    benchmark_fallback: {result['benchmark_fallback']}")
    print(f"    improvement:     {improvement:+.1f}%")
    print(f"    forecast periods: {len(result['periods'])}")
    return {**result, 'series': series_name, 'improvement_pct': improvement}


def test_forecast_accuracy_vs_baseline():
    """
    Runs all synthetic series through the forecasting engine.
    For each series, verifies the chosen method either:
      - beats the naive baseline (validation_mae < benchmark_mae), or
      - falls back to naive with an honest disclosure (benchmark_fallback=True)

    Reports: MAE of chosen method vs naive, % improvement per series.
    """
    series_cases = [
        ('TREND_UP',       TREND_UP),
        ('TREND_DOWN',     TREND_DOWN),
        ('FLAT',           FLAT),
        ('SEASONAL',       SEASONAL),
        ('VOLATILE',       VOLATILE),
        ('MINIMUM_HISTORY',MINIMUM_HISTORY),
    ]

    print(f"\n{'='*60}")
    print(f"FORECAST ACCURACY vs NAIVE BASELINE")
    print(f"{'='*60}")

    results = []
    for name, rows in series_cases:
        result = _run_and_report(name, rows)
        results.append(result)
        print()

    # Aggregate
    improvements = [r['improvement_pct'] for r in results]
    avg_improvement = sum(improvements) / len(improvements)

    print(f"{'='*60}")
    print(f"Average improvement over naive baseline: {avg_improvement:+.1f}%")
    print(f"Fallbacks to naive: "
          f"{sum(1 for r in results if r['benchmark_fallback'])}/{len(results)}")
    print(f"{'='*60}")

    # Assertions: every result is either better than baseline or honestly falling back
    failures = []
    for r in results:
        if r['benchmark_fallback']:
            # Fallback: method was not better; naive is used; this is acceptable
            # but the fallback flag MUST be set truthfully
            if r['validation_mae'] < r['benchmark_mae']:
                failures.append(
                    f"{r['series']}: benchmark_fallback=True but method MAE "
                    f"({r['validation_mae']}) < baseline MAE ({r['benchmark_mae']}) — "
                    "fallback flag is wrong"
                )
        else:
            # No fallback: method must be at least as good as naive
            if r['validation_mae'] > r['benchmark_mae']:
                failures.append(
                    f"{r['series']}: no fallback but validation_mae "
                    f"({r['validation_mae']}) > benchmark_mae ({r['benchmark_mae']})"
                )

    assert not failures, "Forecast accuracy failures:\n" + '\n'.join(failures)


def test_trending_series_beats_naive():
    """
    A clearly trending series (monotone increase) should be forecasted
    by a method better than last_month naive. If not, benchmark_fallback=True.
    """
    result = forecast_months(TREND_UP, horizon=6)
    improvement = _pct_improvement(result['validation_mae'], result['benchmark_mae'])

    print(f"\nTrending series forecast:")
    print(f"  method: {result['method']}, improvement: {improvement:+.1f}%")

    # Either the selected method beats naive, or the system fell back honestly
    if not result['benchmark_fallback']:
        assert result['validation_mae'] <= result['benchmark_mae'], (
            f"Trend series: method={result['method']} has MAE {result['validation_mae']} "
            f"which is worse than naive {result['benchmark_mae']}, but fallback not set"
        )


def test_seasonal_series_picks_seasonal_or_fallback():
    """
    A seasonal series (36 months) should trigger the seasonal_naive method
    or another method that beats naive baseline.
    """
    result = forecast_months(SEASONAL, horizon=6)
    print(f"\nSeasonal series: method={result['method']}, "
          f"fallback={result['benchmark_fallback']}")

    if not result['benchmark_fallback']:
        assert result['validation_mae'] <= result['benchmark_mae'], (
            f"Seasonal series: MAE {result['validation_mae']} worse than "
            f"naive {result['benchmark_mae']}"
        )


def test_forecast_periods_cover_horizon():
    """Forecast output must contain exactly `horizon` future periods."""
    for horizon in (3, 6, 12):
        result = forecast_months(TREND_UP, horizon=horizon)
        assert len(result['periods']) == horizon, (
            f"Expected {horizon} forecast periods, got {len(result['periods'])}"
        )


def test_forecast_intervals_are_ordered():
    """Each forecast period's lower_80 must be <= revenue <= upper_80."""
    result = forecast_months(TREND_UP, horizon=6)
    for p in result['periods']:
        assert p['lower_80'] <= p['revenue'] <= p['upper_80'], (
            f"Period {p['period']}: interval [{p['lower_80']}, {p['upper_80']}] "
            f"does not contain point forecast {p['revenue']}"
        )


def test_forecast_rejects_insufficient_history():
    """Series with fewer than 24 months must be rejected."""
    short = _rows(['5000.00'] * 23)
    with pytest.raises(Exception):
        forecast_months(short)


def test_forecast_rejects_negative_revenue():
    """Negative revenue in history must be rejected."""
    bad = _rows(['-1000.00'] + ['5000.00'] * 24)
    with pytest.raises(Exception):
        forecast_months(bad)


def test_forecast_mae_improvement_reported_as_percentage():
    """Verify the improvement calculation is directionally correct."""
    # If method MAE is half of naive MAE, improvement should be ~50%
    mae_method = D('500.00')
    mae_naive = D('1000.00')
    improvement = _pct_improvement(mae_method, mae_naive)
    assert abs(improvement - 50.0) < 0.01, f"Expected ~50% improvement, got {improvement:.2f}%"

    # If method MAE equals naive, improvement is 0%
    assert _pct_improvement(D('1000.00'), D('1000.00')) == 0.0

    # Zero naive MAE edge case — no division by zero
    assert _pct_improvement(D('0'), D('0')) == 0.0
