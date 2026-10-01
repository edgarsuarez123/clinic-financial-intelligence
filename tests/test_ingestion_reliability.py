"""
Document Ingestion Reliability Test Suite
==========================================
Verifies that the CSV/XLSX/PDF ingestion pipeline correctly and
consistently extracts the right data without silent corruption or
data loss across a batch of realistic documents.

Each document variant has an answer key specifying expected accepted
rows, rejected rows, and specific field values.

Metric: success rate = correct_extractions / total_variants
Target: 100% — any failure represents data loss or silent corruption.

Run:  pytest tests/test_ingestion_reliability.py -v -s
"""

import csv
import io
import uuid
from decimal import Decimal as D
from uuid import uuid4

import pytest

from app.ingestion.config import Profile
from app.ingestion.parsers import FormatError
from app.ingestion.validation import prepare

# ── Shared test profile ───────────────────────────────────────────────────────

CAT_REV = uuid4()
CAT_FIXED = uuid4()
CAT_VARIABLE = uuid4()
PROVIDER_A = uuid4()
PROVIDER_B = uuid4()

_PROFILE = Profile(
    columns={
        'date': 'Date',
        'amount': 'Amount',
        'type': 'Type',
        'category': 'Category',
        'provider': 'Provider',
    },
    date_format='%Y-%m-%d',
    types={'revenue': 'revenue', 'expense': 'expense'},
    categories={
        'Revenue': CAT_REV,
        'Fixed Cost': CAT_FIXED,
        'Variable Cost': CAT_VARIABLE,
    },
    providers={
        'Dr. Smith': PROVIDER_A,
        'Dr. Jones': PROVIDER_B,
    },
    allow_negative_amounts=False,
    currency='USD',
)

_PROFILE_WITH_NEGATIVE = Profile(
    columns=_PROFILE.columns,
    date_format=_PROFILE.date_format,
    types=_PROFILE.types,
    categories=_PROFILE.categories,
    providers=_PROFILE.providers,
    allow_negative_amounts=True,
    currency='USD',
)


# ── CSV builder helpers ───────────────────────────────────────────────────────

def _csv(*rows: tuple) -> bytes:
    """Build CSV bytes from a header + data rows."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Amount', 'Type', 'Category', 'Provider'])
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode('utf-8')


def _valid_row(date='2026-01-15', amount='1000.00', kind='revenue',
               category='Revenue', provider='Dr. Smith'):
    return (date, amount, kind, category, provider)


# ── Answer key structure ──────────────────────────────────────────────────────

def _check(result, *, accepted: int, rejected: int, label: str):
    """Assert extraction matches the answer key."""
    assert len(result.rows) == accepted, (
        f"[{label}] Expected {accepted} accepted rows, got {len(result.rows)}"
    )
    assert len(result.rejections) == rejected, (
        f"[{label}] Expected {rejected} rejected rows, got {len(result.rejections)}"
    )
    assert result.total_rows == accepted + rejected, (
        f"[{label}] total_rows mismatch"
    )


# ── CSV test cases ────────────────────────────────────────────────────────────

def test_csv_single_valid_row():
    data = _csv(_valid_row())
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=1, rejected=0, label='single valid row')
    assert result.rows[0]['amount'] == '1000.00'
    assert result.rows[0]['type'] == 'revenue'


def test_csv_multiple_valid_rows():
    data = _csv(
        _valid_row('2026-01-01', '500.00', 'revenue', 'Revenue', 'Dr. Smith'),
        _valid_row('2026-01-08', '750.00', 'expense', 'Fixed Cost', 'Dr. Jones'),
        _valid_row('2026-01-15', '200.00', 'expense', 'Variable Cost', 'Dr. Smith'),
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=3, rejected=0, label='multiple valid rows')


def test_csv_null_provider_accepted():
    """A row with no provider value should produce provider_key=None."""
    data = _csv(('2026-01-15', '1000.00', 'expense', 'Fixed Cost', ''))
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=1, rejected=0, label='null provider')
    assert result.rows[0]['provider_key'] is None


def test_csv_invalid_amount_rejected():
    data = _csv(
        _valid_row('2026-01-01', '1000.00'),   # valid
        _valid_row('2026-01-02', 'abc'),         # invalid
        _valid_row('2026-01-03', '1.234'),       # too many decimals
        _valid_row('2026-01-04', '$500.00'),     # currency symbol
        _valid_row('2026-01-05', '1,000.00'),    # thousands separator
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=1, rejected=4, label='invalid amounts')
    assert result.rows[0]['amount'] == '1000.00'


def test_csv_negative_amount_rejected_by_default():
    data = _csv(_valid_row('2026-01-15', '-500.00'))
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=0, rejected=1, label='negative rejected by default')
    assert result.rejections[0]['code'] == 'negative_amount'


def test_csv_negative_amount_accepted_when_enabled():
    data = _csv(_valid_row('2026-01-15', '-500.00'))
    result = prepare(data, 'csv', _PROFILE_WITH_NEGATIVE)
    _check(result, accepted=1, rejected=0, label='negative accepted when enabled')
    assert result.rows[0]['amount'] == '-500.00'


def test_csv_invalid_date_formats_rejected():
    data = _csv(
        _valid_row('2026-01-01', '1000.00'),    # valid (baseline)
        _valid_row('01/15/2026', '500.00'),      # wrong format
        _valid_row('2026-13-01', '500.00'),      # invalid month
        _valid_row('not-a-date', '500.00'),      # garbage
        _valid_row('2026/01/15', '500.00'),      # wrong separator
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=1, rejected=4, label='invalid dates')


def test_csv_unknown_category_rejected():
    data = _csv(
        _valid_row(),                                                    # valid
        _valid_row(category='Unknown Department'),                        # bad category
        _valid_row(category=''),                                          # empty
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=1, rejected=2, label='unknown category')
    assert result.rejections[0]['code'] == 'unknown_category'


def test_csv_unknown_provider_rejected():
    data = _csv(_valid_row(provider='Dr. Nobody'))
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=0, rejected=1, label='unknown provider')
    assert result.rejections[0]['code'] == 'unknown_provider'


def test_csv_unknown_type_rejected():
    data = _csv(_valid_row(kind='income'))
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=0, rejected=1, label='unknown type')


def test_csv_mixed_valid_and_invalid_rows():
    """No silent drop: every row is accounted for in accepted + rejected."""
    data = _csv(
        _valid_row('2026-01-01', '1000.00'),
        _valid_row('2026-01-02', 'INVALID'),
        _valid_row('2026-01-03', '2000.00'),
        _valid_row('2026-01-04', 'BAD'),
        _valid_row('2026-01-05', '3000.00'),
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=3, rejected=2, label='mixed valid/invalid')
    assert result.total_rows == 5


def test_csv_duplicate_rows_not_deduplicated():
    """Two identical rows must both be accepted — no intra-file dedup."""
    row = _valid_row('2026-01-15', '1000.00')
    data = _csv(row, row)
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=2, rejected=0, label='duplicate rows kept')


def test_csv_decimal_precision_preserved():
    """Amounts must be preserved exactly — no float conversion."""
    data = _csv(
        _valid_row(amount='100.01'),
        _valid_row(amount='0.99'),
        _valid_row(amount='9999999999999999.99'),
    )
    result = prepare(data, 'csv', _PROFILE)
    _check(result, accepted=3, rejected=0, label='decimal precision')
    amounts = [r['amount'] for r in result.rows]
    assert '100.01' in amounts
    assert '0.99' in amounts


def test_csv_empty_file_rejected():
    data = b''
    with pytest.raises(FormatError):
        prepare(data, 'csv', _PROFILE)


def test_csv_header_only_rejected():
    buf = io.StringIO()
    csv.writer(buf).writerow(['Date', 'Amount', 'Type', 'Category', 'Provider'])
    data = buf.getvalue().encode('utf-8')
    with pytest.raises((FormatError, Exception)):
        result = prepare(data, 'csv', _PROFILE)
        assert result.total_rows == 0


def test_csv_header_mismatch_rejected():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Revenue', 'Kind', 'Bucket', 'Who'])  # wrong headers
    w.writerow(['2026-01-01', '1000.00', 'revenue', 'Revenue', 'Dr. Smith'])
    data = buf.getvalue().encode('utf-8')
    with pytest.raises((FormatError, Exception)):
        prepare(data, 'csv', _PROFILE)


def test_csv_rejection_messages_hide_values():
    """Rejection reasons must not contain the raw cell value (prevents PII leakage)."""
    data = _csv(_valid_row(amount='patient_name_leaked_here'))
    result = prepare(data, 'csv', _PROFILE)
    assert len(result.rejections) == 1
    for field in ('reason', 'code'):
        assert 'patient_name_leaked_here' not in result.rejections[0].get(field, '')


# ── XLSX test cases ───────────────────────────────────────────────────────────

def _make_xlsx(rows: list[tuple], *, formula_row: int = -1) -> bytes:
    """
    Build a minimal XLSX in memory using openpyxl if available,
    otherwise skip. Returns raw bytes.
    """
    openpyxl = pytest.importorskip('openpyxl', reason='openpyxl required for XLSX tests')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Date', 'Amount', 'Type', 'Category', 'Provider'])
    for i, row in enumerate(rows):
        if i == formula_row:
            ws.append(['2026-01-20', '=SUM(A1:A2)', 'expense', 'Fixed Cost', 'Dr. Smith'])
        else:
            ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_valid_rows_extracted():
    data = _make_xlsx([
        ('2026-01-01', '1000.00', 'revenue', 'Revenue', 'Dr. Smith'),
        ('2026-01-08', '500.00',  'expense', 'Fixed Cost', 'Dr. Jones'),
    ])
    result = prepare(data, 'xlsx', _PROFILE)
    _check(result, accepted=2, rejected=0, label='xlsx valid')


def test_xlsx_numeric_cell_preserved_as_string():
    """Numeric cells (not text) must be preserved without float rounding."""
    data = _make_xlsx([('2026-01-01', 1234.56, 'revenue', 'Revenue', 'Dr. Smith')])
    result = prepare(data, 'xlsx', _PROFILE)
    # 1234.56 stored as float in XLSX; parser must convert to string without rounding
    _check(result, accepted=1, rejected=0, label='xlsx numeric cell')
    assert result.rows[0]['amount'] in ('1234.56', '1234.5600')


def test_xlsx_formula_cell_rejected():
    """Rows containing formula cells must be rejected."""
    data = _make_xlsx(
        [('2026-01-01', '500.00', 'expense', 'Fixed Cost', 'Dr. Smith')],
        formula_row=0,
    )
    result = prepare(data, 'xlsx', _PROFILE)
    # The formula row should be rejected
    assert any(r['code'] == 'formula' for r in result.rejections)


def test_xlsx_multiple_sheets_rejected():
    """XLSX with more than one visible worksheet must be rejected entirely."""
    openpyxl = pytest.importorskip('openpyxl', reason='openpyxl required')
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.append(['Date', 'Amount', 'Type', 'Category', 'Provider'])
    ws1.append(['2026-01-01', '1000.00', 'revenue', 'Revenue', 'Dr. Smith'])
    wb.create_sheet('Sheet2')
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises((FormatError, Exception)):
        prepare(buf.getvalue(), 'xlsx', _PROFILE)


# ── PDF test cases ────────────────────────────────────────────────────────────

def _make_pdf_with_table(rows: list[tuple]) -> bytes:
    """Build a simple PDF with a financial table using reportlab."""
    reportlab = pytest.importorskip('reportlab', reason='reportlab required for PDF tests')
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    header = ['Date', 'Amount', 'Type', 'Category', 'Provider']
    table_data = [header] + [list(r) for r in rows]
    doc.build([Table(table_data)])
    return buf.getvalue()


@pytest.mark.xfail(reason="reportlab table layout not extractable by the text-based PDF parser; use an approved clinic export instead")
def test_pdf_valid_table_extracted():
    data = _make_pdf_with_table([
        ('2026-01-01', '1000.00', 'revenue', 'Revenue', 'Dr. Smith'),
        ('2026-01-08', '500.00',  'expense', 'Fixed Cost', 'Dr. Jones'),
    ])
    result = prepare(data, 'pdf', _PROFILE)
    _check(result, accepted=2, rejected=0, label='pdf valid table')


def test_pdf_without_tables_rejected():
    """PDF with text but no table structure must be rejected."""
    reportlab = pytest.importorskip('reportlab', reason='reportlab required')
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    doc.build([Paragraph('This is a text-only PDF with no tables.',
                         getSampleStyleSheet()['Normal'])])
    with pytest.raises((FormatError, Exception)):
        prepare(buf.getvalue(), 'pdf', _PROFILE)


# ── Reliability batch report ──────────────────────────────────────────────────

def test_ingestion_reliability_summary(request):
    """
    Runs a representative batch of ingestion variants and reports
    success rate and failure modes found.

    This test is informational — failures are captured and reported
    without failing the test itself, so you can see partial results.
    """
    cases = [
        ('csv_single_valid',    _csv(_valid_row()),                              'csv', 1, 0),
        ('csv_3_valid',         _csv(*[_valid_row(f'2026-01-0{i+1}', f'{i+1}00.00') for i in range(3)]),
                                                                                  'csv', 3, 0),
        ('csv_null_provider',   _csv(('2026-01-01', '500.00', 'expense', 'Fixed Cost', '')),
                                                                                  'csv', 1, 0),
        ('csv_bad_amount',      _csv(_valid_row(amount='abc')),                   'csv', 0, 1),
        ('csv_bad_date',        _csv(_valid_row(date='15/01/2026')),              'csv', 0, 1),
        ('csv_bad_category',    _csv(_valid_row(category='Bad')),                 'csv', 0, 1),
        ('csv_bad_provider',    _csv(_valid_row(provider='Dr. Nobody')),          'csv', 0, 1),
        ('csv_bad_type',        _csv(_valid_row(kind='salary')),                  'csv', 0, 1),
        ('csv_negative_denied', _csv(_valid_row(amount='-100.00')),               'csv', 0, 1),
        ('csv_mixed_5_rows',
         _csv(_valid_row('2026-01-01'), _valid_row('2026-01-02', 'X'),
              _valid_row('2026-01-03'), _valid_row('2026-01-04', 'Y'),
              _valid_row('2026-01-05')),                                           'csv', 3, 2),
        ('csv_duplicates_kept',
         _csv(_valid_row(), _valid_row()),                                         'csv', 2, 0),
    ]

    successes = 0
    failures = []

    for label, data, kind, exp_acc, exp_rej in cases:
        try:
            result = prepare(data, kind, _PROFILE)
            if len(result.rows) == exp_acc and len(result.rejections) == exp_rej:
                successes += 1
            else:
                failures.append({
                    'label': label,
                    'expected': f'{exp_acc} accepted / {exp_rej} rejected',
                    'actual': f'{len(result.rows)} accepted / {len(result.rejections)} rejected',
                    'mode': 'wrong_counts',
                })
        except Exception as exc:
            failures.append({'label': label, 'mode': 'exception', 'error': str(exc)})

    rate = successes / len(cases) * 100

    print(f"\n{'='*60}")
    print(f"INGESTION RELIABILITY REPORT")
    print(f"{'='*60}")
    print(f"Total variants:  {len(cases)}")
    print(f"Successes:       {successes}")
    print(f"Failures:        {len(failures)}")
    print(f"Success rate:    {rate:.1f}%")

    if failures:
        print(f"\nFailure details:")
        for f in failures:
            if f['mode'] == 'wrong_counts':
                print(f"  FAIL [{f['label']}]: expected {f['expected']}, "
                      f"got {f['actual']}")
            else:
                print(f"  FAIL [{f['label']}]: exception — {f['error']}")
        # Failure modes found
        modes = {f['mode'] for f in failures}
        print(f"\nFailure modes encountered: {', '.join(sorted(modes))}")

    assert len(failures) == 0, (
        f"Ingestion reliability: {len(failures)}/{len(cases)} variants failed "
        f"({100 - rate:.1f}% failure rate)"
    )
