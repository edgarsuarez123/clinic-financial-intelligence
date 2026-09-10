"""Deterministic, fictional clinic fixtures. No patient or real payment records."""
import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import random
import argparse

# Salaries reflect 2025 median compensation for primary care in a mid-size market.
# All names, amounts and employment details are entirely fictional.
STAFF = (
    ('Dr. Elena Rivera',   'Family physician',          '248000'),
    ('Dr. Marcus Bennett', 'Internal medicine physician','262000'),
    ('Dr. Sofia Morales',  'Family physician',          '240000'),
    ('Dr. Daniel Chen',    'Internal medicine physician','255000'),
    ('Isabel Torres NP',   'Nurse practitioner',        '132000'),
    ('Alex Morgan PA',     'Physician assistant',       '126000'),
    ('Camila Ortiz',       'Office manager',             '72000'),
    ('Noah Williams',      'Medical assistant',          '44000'),
    ('Maya Patel',         'Medical assistant',          '45600'),
    ('Lucia Santos',       'Medical biller',             '52000'),
    ('Gabriel Cruz',       'Receptionist',               '40000'),
    ('Emma Brooks',        'Registered nurse',           '84000'),
)

INSURERS = ('Aetna', 'Humana', 'UnitedHealthcare', 'Cigna', 'Triple-S Salud', 'MCS')

# Identifiers only — no copyrighted descriptions or official fee schedules.
CODES = ('99202', '99203', '99212', '99213', '99214')

# Approximate 2025 Medicare national average allowed amounts for primary care E&M.
# Private payers are applied as multipliers below; these are fictional practice values.
MEDICARE_RATES = {'99202': '108', '99203': '160', '99212': '54', '99213': '110', '99214': '163'}

# Payer reimbursement as a fraction of Medicare. Commercial plans pay above Medicare;
# Puerto Rico Medicare Advantage plans (Triple-S, MCS) are closer to Medicare rates.
PAYER_RATE = {
    'UnitedHealthcare': Decimal('1.25'),
    'Aetna':            Decimal('1.22'),
    'Cigna':            Decimal('1.20'),
    'Humana':           Decimal('1.18'),
    'Triple-S Salud':   Decimal('1.08'),
    'MCS':              Decimal('1.05'),
}

# Claim collection rate after denials, write-offs and contractual adjustments.
COLLECTION_RATE = Decimal('0.88')

# E&M code weights reflect a busy primary care panel: high volume of complex
# established patients (99213/99214) and a smaller share of new visits (99202/99203).
CODE_WEIGHTS = {'99202': 8, '99203': 8, '99212': 7, '99213': 35, '99214': 42}

CATEGORIES = {
    'Collections': 'revenue', 'Supplies': 'variable_cost',
    'Salary': 'fixed_cost', 'Benefits': 'fixed_cost', 'Payroll taxes': 'fixed_cost',
    'Malpractice': 'fixed_cost', 'Rent': 'fixed_cost', 'Utilities': 'fixed_cost',
    'Software': 'fixed_cost', 'Insurance': 'fixed_cost',
}

SAMPLE_BILLING_ROWS = 1500


def _two(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def fixture_rows(max_billing_rows: int | None = SAMPLE_BILLING_ROWS):
    rng = random.Random(413)
    staff_rows, billing_rows = [], []
    columns = ['date', 'amount', 'type', 'category', 'provider', 'medical_insurance', 'billing_code']

    day = date(2025, 3, 1)
    while day <= date(2026, 8, 31):
        month_index = (day.year - 2025) * 12 + day.month - 3  # 0–17

        # Seasonal volume index: winter surge (+15%), summer dip (-8%).
        month = day.month
        if month in (12, 1, 2):
            season = Decimal('1.15')
        elif month in (6, 7, 8):
            season = Decimal('0.92')
        else:
            season = Decimal('1.00')

        # Gradual panel growth over 18 months (90% → 100% capacity).
        growth = Decimal('0.90') + Decimal('0.10') * Decimal(month_index) / 17

        if day.weekday() < 5:  # Weekdays only.
            for index, (name, _, _) in enumerate(STAFF[:6]):
                # Daily encounter volume by provider type.
                if index < 4:   # Physicians: 20–26 encounters/day.
                    base_encounters = 20 + rng.randrange(7)
                elif index == 4:  # NP: 15–19.
                    base_encounters = 15 + rng.randrange(5)
                else:             # PA: 14–18.
                    base_encounters = 14 + rng.randrange(5)

                scaled = int((Decimal(base_encounters) * season * growth).to_integral_value())

                for _ in range(max(8, scaled)):
                    payer = rng.choice(INSURERS)
                    code = rng.choices(CODES, weights=[CODE_WEIGHTS[c] for c in CODES])[0]
                    medicare = Decimal(MEDICARE_RATES[code])
                    payer_rate = medicare * PAYER_RATE[payer] * COLLECTION_RATE
                    # ±6% random variation around the payer-adjusted rate.
                    variation = Decimal(rng.randrange(94, 107)) / 100
                    amount = (payer_rate * variation).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    billing_rows.append([day.isoformat(), str(amount), 'revenue', 'Collections', name, payer, code])

        if day.day == calendar.monthrange(day.year, day.month)[1]:
            # Monthly payroll: salary, benefits, payroll taxes, malpractice.
            # Benefits at 30% reflect employer health insurance, 401k match, dental, vision and disability.
            # Payroll taxes at 9.5% cover FICA (7.65%) plus FUTA/SUTA (~1.85%).
            for index, (name, _, annual) in enumerate(STAFF):
                salary = Decimal(annual) / 12
                malpractice = (Decimal('950') if index < 4 else Decimal('400') if index < 6 else Decimal('0'))
                for category, amount in [
                    ('Salary',        salary),
                    ('Benefits',      salary * Decimal('0.30')),
                    ('Payroll taxes', salary * Decimal('0.095')),
                    ('Malpractice',   malpractice),
                ]:
                    if amount:
                        staff_rows.append([day.isoformat(), _two(amount), 'expense', category, name])

        if day.day == 1:
            # Monthly overhead costs.
            # Rent: medical office space for a 6-physician practice.
            # Software: EHR, practice management, billing, telehealth and HIPAA compliance tools.
            # Insurance: general liability, property, cyber liability and umbrella policy.
            # Utilities and supplies vary with patient volume.
            utilities = Decimal(1200 + rng.randrange(600))
            supplies = Decimal(4500 + rng.randrange(1500) + month_index * 60)
            for category, amount in [
                ('Rent',      Decimal('9500')),
                ('Software',  Decimal('2950')),
                ('Insurance', Decimal('1250')),
                ('Utilities', utilities),
                ('Supplies',  supplies),
            ]:
                staff_rows.append([day.isoformat(), str(amount), 'expense', category, ''])

        day += timedelta(days=1)

    # Aggregate daily billing to financial totals per provider/payer/code.
    grouped: dict = {}
    for row_day, amount, kind, category, provider, payer, code in billing_rows:
        key = (row_day, kind, category, provider, payer, code)
        grouped[key] = grouped.get(key, Decimal('0')) + Decimal(amount)
    billing_rows = [[k[0], _two(v), *k[1:]] for k, v in sorted(grouped.items())]

    if max_billing_rows is not None:
        billing_rows = billing_rows[:max_billing_rows]

    return columns, staff_rows, billing_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='write the complete 18-month billing fixture')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / 'examples'
    columns, staff, billing = fixture_rows(None if args.full else SAMPLE_BILLING_ROWS)
    for filename, header, rows in [
        ('staff-costs.csv',    columns[:5], staff),
        ('medical-billing.csv', columns,    billing),
    ]:
        with (directory / filename).open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
    print(f'Wrote {len(staff)} staff rows and {len(billing)} billing rows to {directory}')


if __name__ == '__main__':
    main()
