"""Deterministic, fictional clinic fixtures. No patient or real payment records."""
import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import random
import argparse

STAFF = (
    ('Dr. Elena Rivera', 'Family physician', '216000'),
    ('Dr. Marcus Bennett', 'Internal medicine physician', '228000'),
    ('Dr. Sofia Morales', 'Family physician', '210000'),
    ('Dr. Daniel Chen', 'Internal medicine physician', '222000'),
    ('Isabel Torres NP', 'Nurse practitioner', '126000'),
    ('Alex Morgan PA', 'Physician assistant', '120000'),
    ('Camila Ortiz', 'Office manager', '66000'),
    ('Noah Williams', 'Medical assistant', '42000'),
    ('Maya Patel', 'Medical assistant', '43200'),
    ('Lucia Santos', 'Medical biller', '48000'),
    ('Gabriel Cruz', 'Receptionist', '38400'),
    ('Emma Brooks', 'Registered nurse', '78000'),
)
INSURERS = ('Aetna', 'Humana', 'UnitedHealthcare', 'Cigna', 'Triple-S Salud', 'MCS')
# Identifiers only, no copyrighted code descriptions or actual fee schedules.
CODES = ('99202', '99203', '99212', '99213', '99214')
CATEGORIES = {'Collections': 'revenue', 'Supplies': 'variable_cost',
              'Salary': 'fixed_cost', 'Benefits': 'fixed_cost', 'Payroll taxes': 'fixed_cost',
              'Malpractice': 'fixed_cost', 'Rent': 'fixed_cost', 'Utilities': 'fixed_cost',
              'Software': 'fixed_cost', 'Insurance': 'fixed_cost'}
SAMPLE_BILLING_ROWS = 1500


def fixture_rows(max_billing_rows: int | None = SAMPLE_BILLING_ROWS):
    rng = random.Random(413)
    staff_rows, billing_rows = [], []
    columns = ['date', 'amount', 'type', 'category', 'provider', 'medical_insurance', 'billing_code']
    day = date(2025, 3, 1)
    while day <= date(2026, 8, 31):
        month_index = (day.year - 2025) * 12 + day.month - 3
        if day.weekday() < 5:
            for index, (name, _, _) in enumerate(STAFF[:6]):
                # Daily aggregates per provider, payer and code, never encounter-level records.
                for _ in range(9 + rng.randrange(5)):
                    payer = rng.choice(INSURERS)
                    code = rng.choices(CODES, weights=[1, 2, 1, 5, 6])[0]
                    unit = Decimal({'99202':'74','99203':'108','99212':'58','99213':'91','99214':'132'}[code])
                    amount = (unit * Decimal(rng.randrange(90, 121)) / 100).quantize(Decimal('.01'))
                    billing_rows.append([day.isoformat(), str(amount), 'revenue', 'Collections', name, payer, code])
        if day.day == calendar.monthrange(day.year, day.month)[1]:
            for index, (name, _, annual) in enumerate(STAFF):
                salary = Decimal(annual) / 12
                for category, amount in [('Salary', salary), ('Benefits', salary * Decimal('.18')),
                                         ('Payroll taxes', salary * Decimal('.085')),
                                         ('Malpractice', Decimal('600') if index < 6 else Decimal('0'))]:
                    if amount:
                        staff_rows.append([day.isoformat(), str(amount.quantize(Decimal('.01'))), 'expense', category, name])
        if day.day == 1:
            for category, amount in [('Rent', '6800'), ('Software', '1450'), ('Insurance', '950'),
                                     ('Utilities', str(850 + rng.randrange(300))),
                                     ('Supplies', str(1800 + rng.randrange(600) + month_index * 20))]:
                staff_rows.append([day.isoformat(), amount, 'expense', category, ''])
        day += timedelta(days=1)
    # Combine generated activity into financial aggregates before creating the fixture.
    grouped = {}
    for day, amount, kind, category, provider, payer, code in billing_rows:
        key = (day, kind, category, provider, payer, code)
        grouped[key] = grouped.get(key, Decimal('0')) + Decimal(amount)
    billing_rows = [[key[0], str(amount), *key[1:]] for key, amount in sorted(grouped.items())]
    if max_billing_rows is not None:
        billing_rows = billing_rows[:max_billing_rows]
    return columns, staff_rows, billing_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='write the complete 18-month billing fixture')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / 'examples'
    columns, staff, billing = fixture_rows(None if args.full else SAMPLE_BILLING_ROWS)
    for filename, header, rows in [('staff-costs.csv', columns[:5], staff),
                                   ('medical-billing.csv', columns, billing)]:
        with (directory / filename).open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)


if __name__ == '__main__':
    main()
