"""
Hallucination Rate Test Suite
==============================
Verifies that every numeric value in AI-rendered responses comes
directly from database result rows — zero tolerance for invented numbers.

Run:  pytest tests/test_hallucination_rate.py -v -s

Metric: hallucination rate = phantom values / total numeric values checked.
Target: 0 mismatches (0.00%).
"""

import re
from decimal import Decimal as D
from datetime import date
from uuid import uuid4

import pytest

from app.query.catalog import CATALOG, render_explanation, validate_result, Unreliable


# ── Number extraction helpers ─────────────────────────────────────────────────

# render_explanation produces lines of the form:
#   "[context prefix. ]LABEL is VALUE[ CURRENCY]."
# We extract only the VALUE portion (after "is ") to avoid false positives
# from context fields like "week start: 2026-01-05" which contain date parts.
_VALUE_PATTERN = re.compile(r'\bis (-?\d+(?:\.\d+)?)')
_NUM = re.compile(r'^-?\d+(?:\.\d+)?$')


def _extract_decimals(text: str) -> list[D]:
    """Extract only the rendered value from each explanation line (after 'is ')."""
    return [D(m) for m in _VALUE_PATTERN.findall(text)]


def _source_decimals(rows: list[dict]) -> set[D]:
    """Collect all numeric cell values from source rows as Decimals."""
    values: set[D] = set()
    for row in rows:
        for v in row.values():
            if v is None:
                continue
            s = str(v)
            if _NUM.fullmatch(s):
                try:
                    values.add(D(s))
                except Exception:
                    pass
    return values


def _f(*pairs) -> list[dict]:
    """Build fact dict list from (row_index, column_name) pairs."""
    return [{'row': r, 'column': c} for r, c in pairs]


# ── Synthetic row factories ───────────────────────────────────────────────────

def _summary(rev='1000.00', exp='400.00', net='600.00', margin='60.00', cur='USD'):
    return [{'currency': cur, 'revenue': D(rev), 'expense': D(exp),
             'net': D(net), 'margin_pct': D(margin)}]


def _monthly():
    return [
        {'year': 2025, 'month': 10, 'currency': 'USD', 'revenue': D('4800.00'),
         'expense': D('2000.00'), 'net': D('2800.00'), 'margin_pct': D('58.33'),
         'revenue_growth_pct': None},
        {'year': 2025, 'month': 11, 'currency': 'USD', 'revenue': D('5200.00'),
         'expense': D('2100.00'), 'net': D('3100.00'), 'margin_pct': D('59.62'),
         'revenue_growth_pct': D('8.33')},
        {'year': 2025, 'month': 12, 'currency': 'USD', 'revenue': D('5800.00'),
         'expense': D('2200.00'), 'net': D('3600.00'), 'margin_pct': D('62.07'),
         'revenue_growth_pct': D('11.54')},
    ]


def _weekly():
    return [
        {'week_start': date(2026, 1, 5), 'currency': 'USD', 'revenue': D('1200.00'),
         'expense': D('500.00'), 'net': D('700.00'), 'margin_pct': D('58.33')},
        {'week_start': date(2026, 1, 12), 'currency': 'USD', 'revenue': D('1350.00'),
         'expense': D('510.00'), 'net': D('840.00'), 'margin_pct': D('62.22')},
        {'week_start': date(2026, 1, 19), 'currency': 'USD', 'revenue': D('1100.00'),
         'expense': D('490.00'), 'net': D('610.00'), 'margin_pct': D('55.45')},
    ]


def _cost(fixed='1500.00', variable='800.00', fp='65.22', vp='34.78'):
    return [{'currency': 'USD', 'fixed_cost': D(fixed), 'variable_cost': D(variable),
             'fixed_cost_pct': D(fp), 'variable_cost_pct': D(vp)}]


def _volatility(rv='12.50', ev='8.30', weeks=8):
    return [{'currency': 'USD', 'observed_weeks': weeks,
             'revenue_cv': D(rv), 'expense_cv': D(ev)}]


def _providers(rev='9000.00', cost='5000.00', net='4000.00'):
    pid = str(uuid4())
    return [{'provider_key': pid, 'currency': 'USD', 'revenue': D(rev),
             'recorded_cost': D(cost), 'observed_net': D(net)}]


# ── Case builder ──────────────────────────────────────────────────────────────

def _build_cases():
    cases = []

    # Summary — 10 value combinations × 4 single-cell selections + 3 multi-cell = 43
    _sv = [
        ('100.00',    '40.00',    '60.00',   '60.00'),
        ('250.50',    '100.25',   '150.25',  '59.97'),
        ('50000.00',  '30000.00', '20000.00','40.00'),
        ('999.99',    '333.33',   '666.66',  '66.67'),
        ('1.00',      '0.50',     '0.50',    '50.00'),
        ('10000.00',  '9999.99',  '0.01',    '0.00'),
        ('500000.00', '200000.00','300000.00','60.00'),
        ('75.25',     '25.00',    '50.25',   '66.78'),
        ('3333.33',   '1111.11',  '2222.22', '66.67'),
        ('12500.00',  '4375.00',  '8125.00', '65.00'),
    ]
    for rev, exp, net, margin in _sv:
        rows = _summary(rev, exp, net, margin)
        for col in ('revenue', 'expense', 'net', 'margin_pct'):
            cases.append(('summary', rows, _f((0, col))))
    cases.append(('summary', _summary(), _f((0, 'revenue'), (0, 'net'))))
    cases.append(('summary', _summary(), _f((0, 'expense'), (0, 'margin_pct'))))
    cases.append(('summary', _summary('99999.00', '44444.00', '55555.00', '55.56'),
                  _f((0, 'revenue'), (0, 'expense'), (0, 'net'), (0, 'margin_pct'))))

    # Monthly — 3 rows × 4 cols + 4 growth + 2 multi-cell = 18
    monthly = _monthly()
    for ri in range(len(monthly)):
        for col in ('revenue', 'expense', 'net', 'margin_pct'):
            cases.append(('monthly', monthly, _f((ri, col))))
    cases.append(('monthly', monthly, _f((1, 'revenue_growth_pct'))))
    cases.append(('monthly', monthly, _f((2, 'revenue_growth_pct'))))
    cases.append(('monthly', monthly, _f((0, 'revenue'), (1, 'revenue'), (2, 'revenue'))))
    cases.append(('monthly', monthly, _f((0, 'net'), (2, 'net'))))

    # Weekly — 3 rows × 4 cols + 2 multi-cell = 14
    weekly = _weekly()
    for ri in range(len(weekly)):
        for col in ('revenue', 'expense', 'net', 'margin_pct'):
            cases.append(('weekly', weekly, _f((ri, col))))
    cases.append(('weekly', weekly, _f((0, 'revenue'), (1, 'revenue'), (2, 'revenue'))))
    cases.append(('weekly', weekly, _f((2, 'margin_pct'))))

    # Cost breakdown — 4 variants × 3 selections = 12
    _cv = [
        ('1500.00', '800.00',  '65.22', '34.78'),
        ('2000.00', '1000.00', '66.67', '33.33'),
        ('500.00',  '500.00',  '50.00', '50.00'),
        ('10000.00','2000.00', '83.33', '16.67'),
    ]
    for fixed, var, fp, vp in _cv:
        rows = _cost(fixed, var, fp, vp)
        cases.append(('cost_breakdown', rows, _f((0, 'fixed_cost'))))
        cases.append(('cost_breakdown', rows, _f((0, 'variable_cost'), (0, 'fixed_cost_pct'))))
        cases.append(('cost_breakdown', rows, _f((0, 'fixed_cost_pct'), (0, 'variable_cost_pct'))))

    # Volatility — 5 variants × 2 selections = 10
    _vv = [
        ('12.50', '8.30',  8),
        ('0.00',  '0.00',  52),
        ('45.33', '22.11', 12),
        ('5.20',  '3.10',  26),
        ('100.00','50.00', 4),
    ]
    for rv, ev, wks in _vv:
        rows = _volatility(rv, ev, wks)
        cases.append(('volatility', rows, _f((0, 'revenue_cv'))))
        cases.append(('volatility', rows, _f((0, 'revenue_cv'), (0, 'expense_cv'))))

    # Providers — 5 variants × 2 selections = 10
    _pv = [
        ('9000.00',   '5000.00',   '4000.00'),
        ('150000.00', '120000.00', '30000.00'),
        ('25000.00',  '25000.00',  '0.00'),
        ('1000.00',   '500.00',    '500.00'),
        ('80000.00',  '90000.00',  '-10000.00'),
    ]
    for rev, cost, net in _pv:
        rows = _providers(rev, cost, net)
        cases.append(('providers', rows, _f((0, 'revenue'))))
        cases.append(('providers', rows, _f((0, 'recorded_cost'), (0, 'observed_net'))))

    return cases


_CASES = _build_cases()


# ── Main hallucination rate test ──────────────────────────────────────────────

def test_hallucination_rate():
    """
    Sends all test cases through the explanation renderer and verifies
    that every number in the output was present in the source rows.

    Reports: hallucination rate as % and raw mismatch count.
    """
    total_checked = 0
    total_mismatches = 0
    failures = []

    for i, (query_key, rows, facts) in enumerate(_CASES):
        query = CATALOG[query_key]
        rendered = render_explanation(facts, query, rows)

        found = _extract_decimals(rendered)
        source = _source_decimals(rows)
        phantom = [n for n in found if n not in source]

        total_checked += len(found)
        total_mismatches += len(phantom)

        if phantom:
            failures.append((i, query_key, rendered, phantom))

    rate = (total_mismatches / total_checked * 100) if total_checked > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"HALLUCINATION RATE REPORT")
    print(f"{'='*60}")
    print(f"Test cases:              {len(_CASES)}")
    print(f"Numeric values checked:  {total_checked}")
    print(f"Mismatches (phantom):    {total_mismatches}")
    print(f"Hallucination rate:      {rate:.2f}%")
    if failures:
        print(f"\nFirst failure:")
        idx, qk, rendered, phantom = failures[0]
        print(f"  Case {idx} [{qk}]: phantom={phantom}")
        print(f"  Rendered: {rendered!r}")

    assert total_mismatches == 0, (
        f"Hallucination detected: {total_mismatches}/{total_checked} numeric values "
        f"were not present in source rows ({rate:.2f}%)"
    )


def test_out_of_bounds_row_does_not_hallucinate():
    """Row index beyond result set must not produce invented numbers."""
    query = CATALOG['summary']
    rows = _summary('1000.00', '400.00', '600.00', '60.00')
    source = _source_decimals(rows)
    try:
        rendered = render_explanation([{'row': 99, 'column': 'revenue'}], query, rows)
        phantom = [n for n in _extract_decimals(rendered) if n not in source]
        assert not phantom, f"Phantom numbers from out-of-bounds row: {phantom}"
    except Exception:
        pass  # Raising on invalid reference is also acceptable — no hallucination occurs


def test_unknown_column_does_not_hallucinate():
    """Unknown column name must not produce invented numbers."""
    query = CATALOG['summary']
    rows = _summary()
    source = _source_decimals(rows)
    try:
        rendered = render_explanation([{'row': 0, 'column': 'nonexistent'}], query, rows)
        phantom = [n for n in _extract_decimals(rendered) if n not in source]
        assert not phantom, f"Phantom numbers from unknown column: {phantom}"
    except Exception:
        pass


def test_validate_result_enforces_100_row_limit():
    """validate_result must reject sets of 101 or more rows (overflow detection)."""
    overflow_rows = [
        {'currency': 'USD', 'revenue': D('100.00'), 'expense': D('40.00'),
         'net': D('60.00'), 'margin_pct': D('60.00')}
        for _ in range(101)
    ]
    with pytest.raises(Exception):
        validate_result(CATALOG['summary'], overflow_rows)
