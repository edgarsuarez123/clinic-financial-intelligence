"""Resolve explicitly chosen history, then call the pure simulation engine."""
from .calculations import Hire,StaffGroup,ClinicCost,ClinicPlan,Scenario,RampStep,anniversary,historical_baseline,clinic_sensitivity

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
        hire=Hire(role_type=s.role_type,revenue_mechanism='incremental_practice' if s.revenue_mode=='incremental' else 'none',
            start_date=anniversary(body.start_date,s.start_month-1),months=s.end_month-s.start_month+1,currency=body.currency,
            monthly_revenue=revenue,revenue_basis=basis,**s.model_dump(include={'annual_salary','benefits_pct','payroll_tax_pct','annual_malpractice','annual_other_fixed_cost','onboarding_cost','variable_cost_pct','cost_basis','headcount'}))
        groups.append(StaffGroup(hire,s.start_month,s.revenue_mode))
    plan=ClinicPlan(body.start_date,body.months,body.currency,body.existing_monthly_revenue,
        body.existing_revenue_basis,tuple(groups),tuple(ClinicCost(**c.model_dump()) for c in body.clinic_costs),body.existing_revenue_by_month)
    scenarios=tuple(Scenario(s.name,s.revenue_multiplier,s.fixed_cost_multiplier,tuple(RampStep(**r.model_dump()) for r in s.ramp),s.ramp_basis) for s in body.scenarios)
    result=clinic_sensitivity(plan,scenarios)
    return result
