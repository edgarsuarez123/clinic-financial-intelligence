import csv
from datetime import date
from decimal import Decimal as D
from pathlib import Path
import unittest
from app.analytics.calculations import Transaction
from app.simulation.baseline import clinic_baseline
from app.demo_data import fixture_rows, STAFF, INSURERS, CODES, CATEGORIES


class BaselineTests(unittest.TestCase):
    def test_actual_average_includes_payroll(self):
        rows = [Transaction(date(2026, month, 1), D(amount), kind, key, classification)
                for month in (1, 2, 3)
                for amount, kind, key, classification in [('10000', 'revenue', 'r', 'revenue'),
                    ('6000', 'expense', 's', 'fixed_cost'), ('1000', 'expense', 'c', 'fixed_cost')]]
        value = clinic_baseline(rows, date(2026, 1, 1), date(2026, 3, 31), {'s':'Salary','c':'Rent'})
        self.assertEqual(value['existing_monthly_revenue'], D('10000'))
        self.assertEqual(sum(c['monthly_amount'] for c in value['costs']), D('7000'))
        self.assertIn('add only incremental', value['basis'])

    def test_empty_partial_and_missing_months_are_rejected(self):
        rows = [Transaction(date(2026, 1, 1), D('100'), 'revenue', 'r', 'revenue')]
        for data, start, end in [([], date(2026,1,1), date(2026,1,31)),
                (rows, date(2026,1,2), date(2026,1,31)),
                (rows, date(2026,1,1), date(2026,2,28))]:
            with self.assertRaises(ValueError): clinic_baseline(data,start,end,{})

    def test_repeating_averages_fit_decimal_input_contract(self):
        rows = [Transaction(date(2026, month, 1), D(amount), 'revenue', 'r', 'revenue')
                for month, amount in [(1,'1'),(2,'1'),(3,'2')]]
        value=clinic_baseline(rows,date(2026,1,1),date(2026,3,31),{})
        self.assertEqual(str(value['existing_monthly_revenue']), '1.33')

    def test_fixtures_reproduce_and_are_financial_only(self):
        columns, staff, billing = fixture_rows(None)
        self.assertEqual(len(STAFF),12)
        self.assertGreater(len(billing),1000)
        self.assertEqual({r[5] for r in billing},set(INSURERS))
        self.assertEqual({r[6] for r in billing},set(CODES))
        self.assertEqual({r[4] for r in staff if r[4]}, {s[0] for s in STAFF})
        for name, header, rows in [('staff-costs.csv',columns[:5],staff),('medical-billing.csv',columns,billing)]:
            with (Path('examples')/name).open() as stream:
                self.assertEqual(list(csv.reader(stream)), [header, *rows])
            self.assertLess((Path('examples')/name).stat().st_size,10*1024*1024)
            for row in rows:
                self.assertIn(row[3], CATEGORIES)
                self.assertEqual(D(row[1]),D(row[1]).quantize(D('.01')))
        self.assertGreater(len(fixture_rows(None)[2]),20000)


if __name__ == '__main__': unittest.main()
