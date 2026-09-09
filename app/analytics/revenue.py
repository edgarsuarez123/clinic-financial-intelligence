"""Pure Decimal revenue analysis. Filters never redistribute unclassified revenue."""
from collections import defaultdict
from datetime import timedelta
from .calculations import ZERO, exact, check_range, period_start, next_period

DIMENSIONS=('medical_insurance','billing_code','category')

@exact
def revenue_report(records,start,end,frequency='month',filters=None):
    check_range(start,end)
    period_start(start,frequency)  # validate even with no observations
    filters=filters or {}
    if set(filters)-set(DIMENSIONS): raise ValueError('Unknown revenue filter')
    available=[r for r in records if start<=r['full_date']<=end]
    # Empty string is a filter token for unclassified; null means no filter.
    options={key:sorted({r.get(key) or '' for r in available}) for key in DIMENSIONS}
    selected=[r for r in available if all(value is None or (r.get(key) or '')==value for key,value in filters.items())]
    groups=defaultdict(list)
    for row in selected: groups[period_start(row['full_date'],frequency)].append(row)
    periods=[]; current=period_start(start,frequency)
    while current<=end:
        following=next_period(current,frequency); last=following-timedelta(days=1)
        rows=groups[current]
        periods.append({'period_start':current,'period_end':last,'coverage_start':max(start,current),
            'coverage_end':min(end,last),'partial':current<start or last>end,
            'revenue':sum((r['amount'] for r in rows),ZERO) if rows else None,'row_count':len(rows)})
        current=following
    breakdowns={}
    for key in DIMENSIONS:
        totals=defaultdict(lambda:ZERO)
        for row in selected: totals[row.get(key) or '']+=row['amount']
        breakdowns[key]=[{'value':label,'label':label or 'Not classified','revenue':amount}
            for label,amount in sorted(totals.items(),key=lambda item:(-item[1],item[0]))]
    return {'total_revenue':sum((r['amount'] for r in selected),ZERO) if selected else None,
            'row_count':len(selected),'periods':periods,'breakdowns':breakdowns,'options':options,
            'frequency':frequency,'filters':filters}
