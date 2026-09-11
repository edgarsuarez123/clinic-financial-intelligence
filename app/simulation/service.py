"""Resolve explicitly chosen history, then call the pure simulation engine."""
from .calculations import Hire,StaffGroup,ClinicCost,ClinicPlan,Scenario,RampStep,anniversary,historical_baseline,clinic_sensitivity
from decimal import Decimal
from ..analytics.calculations import exact

@exact
def calculate(body,repo,uid,rid):
    groups=[]; history={}
    for s in body.staff:
        source=s.revenue
        if source.kind=='manual':
            if source.monthly_revenue is None or source.provider_keys or source.start or source.end:
                raise ValueError('Manual revenue requires an explicit amount and no historical selectors')
            revenue=source.monthly_revenue; basis={'kind':'manual','basis':source.basis}
        else:
            if source.monthly_revenue is not None or not source.start or not source.end or not source.provider_keys or s.revenue_mode!='incremental':
                raise ValueError('Historical revenue requires dates, providers and incremental mode, with no manual amount')
            from ..analytics.calculations import check_range
            check_range(source.start,source.end)
            key=(source.start,source.end)
            if key not in history: history[key]=repo.rows(uid,rid,*key,providers=True)
            rows,currency=history[key]
            if currency!=body.currency: raise ValueError('Historical and plan currencies must match')
            basis=historical_baseline(rows,[str(k) for k in source.provider_keys],*key)
            basis['application_basis']=source.basis
            revenue=basis['monthly_revenue']
        if any(m<s.start_month or m>s.end_month for m in s.monthly_salary): raise ValueError('Salary override is outside the employment schedule')
        hire=Hire(role_type=s.role_type,revenue_mechanism='incremental_practice' if s.revenue_mode=='incremental' else 'none',
            monthly_salary={m-s.start_month+1:v for m,v in s.monthly_salary.items()},
            start_date=anniversary(body.start_date,s.start_month-1),months=s.end_month-s.start_month+1,currency=body.currency,
            monthly_revenue=revenue,revenue_basis=basis,**s.model_dump(include={'annual_salary','benefits_pct','payroll_tax_pct','annual_malpractice','annual_other_fixed_cost','onboarding_cost','variable_cost_pct','cost_basis','headcount'}))
        groups.append(StaffGroup(hire,s.start_month,s.revenue_mode))
    revenue_by_month=dict(body.existing_revenue_by_month)
    if body.revenue_mode=='drivers':
        if not body.revenue_drivers: raise ValueError('Add at least one revenue driver')
        if body.existing_revenue_by_month: raise ValueError('Amount overrides and driver-based revenue cannot be combined')
        for driver in body.revenue_drivers:
            if any(m<1 or m>body.months for m in {*driver.units_by_month,*driver.payment_by_month}): raise ValueError('Revenue driver override is outside the plan horizon')
        revenue_by_month={m:sum((d.units_by_month.get(m,d.monthly_units)*d.payment_by_month.get(m,d.collected_per_unit) for d in body.revenue_drivers),Decimal('0')) for m in range(1,body.months+1)}
    plan=ClinicPlan(body.start_date,body.months,body.currency,body.existing_monthly_revenue,
        body.existing_revenue_basis,tuple(groups),tuple(ClinicCost(**c.model_dump()) for c in body.clinic_costs),revenue_by_month,body.variable_cost_pct)
    for s in body.scenarios:
        if s.volume_multiplier>3 or s.payment_multiplier>3: raise ValueError('Volume and payment multipliers must be between 0 and 3')
    scenarios=tuple(Scenario(s.name,s.revenue_multiplier*s.volume_multiplier*s.payment_multiplier,s.fixed_cost_multiplier,tuple(RampStep(**r.model_dump()) for r in s.ramp),s.ramp_basis) for s in body.scenarios)
    result=clinic_sensitivity(plan,scenarios)
    result['input_plan']=body.model_dump(mode='json')
    if body.baseline:
        # Snapshot values are preserved from the explicit baseline review, not re-queried on save.
        base_revenue=body.baseline.revenue
        base_cost=sum((c.monthly_amount for c in body.baseline.costs),Decimal('0'))
        for output in result['scenarios']:
            output['baseline_comparison']={'monthly_revenue':base_revenue,'monthly_cost':base_cost,
                'monthly_net':base_revenue-base_cost,
                'projected_net_change':output['summary']['net']-(base_revenue-base_cost)*body.months}
            for period in output['periods']: period['net_change']=period['net']-(base_revenue-base_cost)
    return result
