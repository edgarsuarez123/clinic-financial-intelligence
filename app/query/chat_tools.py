"""Typed, bounded what-if edits. These return drafts and never save a budget."""
from copy import deepcopy
from decimal import Decimal
from ..analytics.calculations import exact
from ..simulation.schemas import PlanInput

@exact
def apply_changes(plan,changes):
    draft=deepcopy(plan)
    if not changes: raise ValueError('Specify at least one change for the draft.')
    for change in changes:
        first=change.from_month;last=min(change.through_month,draft['months'])
        if first>last: raise ValueError('Change is outside the plan timeline.')
        factor=1+change.percent/100
        def adjusted(v): return format((Decimal(str(v))*factor).quantize(Decimal('.01')),'f')
        if change.kind=='revenue_percent':
            if draft.get('revenue_mode')=='drivers': raise ValueError('Change units or collected payment for a driver-based plan.')
            values=draft.setdefault('existing_revenue_by_month',{})
            for m in range(first,last+1): values[str(m)]=adjusted(values.get(str(m),draft['existing_monthly_revenue']))
        elif change.kind in {'cost_percent','salary_percent'}:
            items=draft['clinic_costs'] if change.kind=='cost_percent' else draft['staff']
            if change.row_index>=len(items): raise ValueError('The selected cost or staff row does not exist.')
            row=items[change.row_index]
            values=row.setdefault('monthly_amounts' if change.kind=='cost_percent' else 'monthly_salary',{})
            base=row['monthly_amount'] if change.kind=='cost_percent' else Decimal(row['annual_salary'])/12
            for m in range(max(first,row['start_month']),min(last,row['end_month'])+1): values[str(m)]=adjusted(values.get(str(m),base))
        elif change.kind in {'driver_units_percent','driver_payment_percent'}:
            items=draft.get('revenue_drivers',[])
            if draft.get('revenue_mode')!='drivers' or change.row_index>=len(items): raise ValueError('Choose an existing revenue driver.')
            row=items[change.row_index];units=change.kind=='driver_units_percent'
            values=row.setdefault('units_by_month' if units else 'payment_by_month',{})
            for m in range(first,last+1): values[str(m)]=adjusted(values.get(str(m),row['monthly_units' if units else 'collected_per_unit']))
        else:
            if change.row_index>=len(draft['staff']): raise ValueError('Choose an existing staff group.')
            row=draft['staff'][change.row_index];offset=first-row['start_month']
            if row['end_month']+offset>draft['months']: raise ValueError('Moving this hire would exceed the plan horizon. Extend the plan first.')
            row['start_month']=first;row['end_month']+=offset
            row['monthly_salary']={str(int(m)+offset):v for m,v in row.get('monthly_salary',{}).items()}
    return PlanInput.model_validate(draft)
