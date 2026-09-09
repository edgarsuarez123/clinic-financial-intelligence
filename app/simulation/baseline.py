"""Snapshot recorded monthly actuals without imputing missing months."""
from decimal import Decimal
from ..analytics.calculations import exact, period_series


@exact
def clinic_baseline(rows, start, end, labels):
    periods = period_series(rows, start, end, 'month')
    if any(p['partial'] or not p['observed'] for p in periods):
        raise ValueError('Select complete calendar months with recorded activity in every month.')
    count = Decimal(len(periods))
    categories = {}
    for period in periods:
        for category in period['categories']:
            key = category['category_key']
            categories[key] = categories.get(key, Decimal('0')) + category['amount']
    revenue = sum((p['revenue'] for p in periods), Decimal('0')) / count
    costs = [{'label': labels.get(key, key), 'monthly_amount': (amount / count).quantize(Decimal('.01'))}
             for key, amount in sorted(categories.items())]
    if revenue < 0 or any(c['monthly_amount'] < 0 for c in costs):
        raise ValueError('Negative historical baselines require manual review.')
    if len(costs) > 50:
        raise ValueError('This baseline exceeds 50 cost categories; use a smaller scope or a manual plan.')
    return {'existing_monthly_revenue': revenue.quantize(Decimal('.01')), 'costs': costs,
            'basis': f'Recorded monthly average, {start} through {end}, {len(periods)} months. '
                     'Includes recorded payroll and overhead; add only incremental staff/costs. '
                     'Monthly averages rounded to cents. Assumes complete books and recurring costs; review one-time expenses. No seasonality inferred.'}
