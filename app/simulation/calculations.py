"""Pure, deterministic staffing projections; no database, web or UI dependency."""
import calendar
from dataclasses import dataclass,asdict,field
from datetime import date,timedelta
from decimal import Decimal
from ..analytics.calculations import exact,check_range,period_start,next_period

ZERO=Decimal('0'); ONE=Decimal('1'); HUNDRED=Decimal('100'); TWELVE=Decimal('12')

def decimal_between(value,low,high):
    if not isinstance(value,Decimal) or not value.is_finite() or not low<=value<=high:
        raise ValueError('A finite Decimal within the supported range is required')

@dataclass(frozen=True)
class RampStep:
    month: int
    productivity: Decimal
    def __post_init__(self):
        if type(self.month) is not int or not 1<=self.month<=120: raise ValueError('Invalid ramp month')
        decimal_between(self.productivity,ZERO,ONE)

@dataclass(frozen=True)
class Hire:
    role_type: str
    revenue_mechanism: str
    start_date: date
    months: int
    currency: str
    annual_salary: Decimal
    benefits_pct: Decimal
    annual_malpractice: Decimal
    annual_other_fixed_cost: Decimal
    onboarding_cost: Decimal
    variable_cost_pct: Decimal
    cost_basis: str
    monthly_revenue: Decimal
    revenue_basis: dict
    payroll_tax_pct: Decimal = ZERO
    headcount: int = 1
    monthly_salary: dict[int,Decimal] = field(default_factory=dict)

    def __post_init__(self):
        if not self.role_type.strip() or not self.cost_basis.strip(): raise ValueError('Role and cost basis are required')
        if self.revenue_mechanism not in {'direct_provider','incremental_practice','none'}: raise ValueError('Invalid revenue mechanism')
        if type(self.start_date) is not date or not 1900<=self.start_date.year<=2189: raise ValueError('Invalid start date')
        if type(self.months) is not int or not 1<=self.months<=120: raise ValueError('Horizon must be 1–120 months')
        if len(self.currency)!=3 or not self.currency.isascii() or not self.currency.isupper() or not self.currency.isalpha(): raise ValueError('Explicit three-letter currency required')
        for value in (self.annual_salary,self.annual_malpractice,self.annual_other_fixed_cost,self.onboarding_cost,self.monthly_revenue):
            decimal_between(value,ZERO,Decimal('1000000000000'))
        decimal_between(self.benefits_pct,ZERO,Decimal('200'))
        decimal_between(self.variable_cost_pct,ZERO,HUNDRED)
        if self.revenue_mechanism=='none' and self.monthly_revenue!=ZERO: raise ValueError('A cost-only role must have zero modeled revenue')
        if not self.revenue_basis: raise ValueError('Revenue provenance is required')
        decimal_between(self.payroll_tax_pct,ZERO,HUNDRED)
        if type(self.headcount) is not int or not 1<=self.headcount<=500: raise ValueError('Headcount must be 1–500')
        for month,value in self.monthly_salary.items():
            if type(month) is not int or not 1<=month<=self.months: raise ValueError('Salary override is outside the employment schedule')
            decimal_between(value,ZERO,Decimal('1000000000000'))

@dataclass(frozen=True)
class Scenario:
    name: str
    revenue_multiplier: Decimal
    fixed_cost_multiplier: Decimal
    ramp: tuple[RampStep,...]
    ramp_basis: str
    def __post_init__(self):
        if self.name not in {'pessimistic','expected','optimistic'}: raise ValueError('Invalid scenario name')
        decimal_between(self.revenue_multiplier,ZERO,Decimal('3'))
        decimal_between(self.fixed_cost_multiplier,ZERO,Decimal('3'))
        if not self.ramp or self.ramp[0].month!=1 or not self.ramp_basis.strip(): raise ValueError('Ramp must start at month 1 with an explicit basis')
        months=[x.month for x in self.ramp]
        if months!=sorted(set(months)): raise ValueError('Ramp months must be unique and increasing')

def anniversary(anchor,offset):
    ordinal=anchor.year*12+anchor.month-1+offset
    year,month=divmod(ordinal,12); month+=1
    return date(year,month,min(anchor.day,calendar.monthrange(year,month)[1]))

@exact
def project(hire,scenario):
    salary=hire.annual_salary/TWELVE*scenario.fixed_cost_multiplier*hire.headcount
    benefits=hire.annual_salary/TWELVE*hire.benefits_pct/HUNDRED*scenario.fixed_cost_multiplier*hire.headcount
    malpractice=hire.annual_malpractice/TWELVE*scenario.fixed_cost_multiplier*hire.headcount
    other=hire.annual_other_fixed_cost/TWELVE*scenario.fixed_cost_multiplier*hire.headcount
    payroll_taxes=hire.annual_salary/TWELVE*hire.payroll_tax_pct/HUNDRED*scenario.fixed_cost_multiplier*hire.headcount
    recurring=salary+benefits+malpractice+other+payroll_taxes
    cumulative_revenue=ZERO; cumulative_cost=ZERO; periods=[]
    peak_deficit=hire.onboarding_cost*hire.headcount; first=None
    for month in range(1,hire.months+1):
        salary=hire.monthly_salary.get(month,hire.annual_salary/TWELVE)*scenario.fixed_cost_multiplier*hire.headcount
        benefits=salary*hire.benefits_pct/HUNDRED
        payroll_taxes=salary*hire.payroll_tax_pct/HUNDRED
        recurring=salary+benefits+malpractice+other+payroll_taxes
        productivity=next(step.productivity for step in reversed(scenario.ramp) if step.month<=month)
        revenue=hire.monthly_revenue*scenario.revenue_multiplier*productivity*hire.headcount
        variable=revenue*hire.variable_cost_pct/HUNDRED
        onboarding=hire.onboarding_cost*hire.headcount if month==1 else ZERO
        cost=recurring+variable+onboarding
        cumulative_revenue+=revenue; cumulative_cost+=cost
        balance=cumulative_revenue-cumulative_cost
        peak_deficit=max(peak_deficit,-balance)
        beginning=anniversary(hire.start_date,month-1)
        ending=anniversary(hire.start_date,month)-timedelta(days=1)
        if first is None and balance>=ZERO: first={'month':month,'period_end':ending}
        periods.append({'month':month,'start':beginning,'end':ending,'productivity':productivity,
            'revenue':revenue,'salary':salary,'benefits':benefits,'malpractice':malpractice,
            'other_fixed_cost':other,'payroll_taxes':payroll_taxes,'variable_cost':variable,'onboarding_cost':onboarding,
            'total_cost':cost,'net':revenue-cost,'cumulative_revenue':cumulative_revenue,
            'cumulative_cost':cumulative_cost,'cumulative_net':balance})
    sustained=None
    for item in reversed(periods):
        if item['cumulative_net']<ZERO: break
        sustained={'month':item['month'],'period_end':item['end']}
    assumptions={**asdict(hire),'scenario':asdict(scenario),
        'ramp_status':'Assumption; not calibrated from historical hiring data.',
        'period_convention':'Full hire-relative monthly periods; annual costs divided by 12. Anniversary dates clamp to month end without drifting. No daily proration.',
        'timing':'Onboarding is paid at hire; other costs and revenue are modeled at period close. Collections delays and intra-period working capital are not modeled.',
        'fixed_cost_multiplier_scope':'Salary, salary-based benefits and effective payroll taxes, malpractice and other annual fixed costs only. Onboarding and revenue-based variable costs are not scaled by it.',
        'tax_convention':'Payroll tax is a user-entered effective percentage of base salary, not a jurisdiction-specific tax calculation; caps and employer-specific rules are not inferred.',
        'per_person_convention':'Pay, insurance, onboarding and revenue inputs are per employee and multiplied by headcount.',
        'projection_scope':'Incremental hire contribution, not whole-practice profit. No inflation, taxes on profit, financing or residual value unless explicitly represented in the entered costs.',
        'break_even_definition':'First modeled period close with cumulative revenue >= cumulative cost; no exact intra-month date is inferred.'}
    return {'scenario':scenario.name,'assumptions':assumptions,'periods':periods,
        'summary':{'total_revenue':cumulative_revenue,'total_cost':cumulative_cost,
            'net':cumulative_revenue-cumulative_cost,'first_break_even':first,
            'sustained_break_even_within_horizon':sustained,
            'break_even_status':'no_costs' if cumulative_cost==ZERO else ('reached' if first else 'not_reached_within_horizon'),
            'peak_modeled_deficit':max(ZERO,peak_deficit)}}

@exact
def sensitivity(hire,scenarios):
    if len(scenarios)!=3 or {s.name for s in scenarios}!={'pessimistic','expected','optimistic'}:
        raise ValueError('Supply exactly pessimistic, expected and optimistic scenarios')
    by_name={s.name:s for s in scenarios}
    outputs=[project(hire,by_name[name]) for name in ('pessimistic','expected','optimistic')]
    ordered=outputs[0]['summary']['net']<=outputs[1]['summary']['net']<=outputs[2]['summary']['net']
    return {'scenarios':outputs,'ordering_note':None if ordered else
            'The entered scenario assumptions do not produce pessimistic <= expected <= optimistic final net. Review the labels and inputs.'}

@exact
def historical_baseline(rows,provider_keys,start,end):
    check_range(start,end)
    keys=set(provider_keys)
    if not keys or len(keys)!=len(provider_keys): raise ValueError('Select distinct provider identifiers')
    months=[]; month=period_start(start,'month')
    while month<=end:
        following=next_period(month,'month')
        if month>=start and following-timedelta(days=1)<=end: months.append(month)
        month=following
    totals={}
    for row in rows:
        month=period_start(row.date,'month')
        if row.type=='revenue' and row.provider_key in keys and month in months:
            key=(row.provider_key,month)
            totals[key]=totals.get(key,ZERO)+row.amount
    if not totals or any(not any(key[0]==provider for key in totals) for provider in keys):
        raise ValueError('Each selected provider needs revenue observations in at least one fully selected calendar month')
    revenue=sum(totals.values(),ZERO)/Decimal(len(totals))
    if revenue<ZERO: raise ValueError('A negative historical baseline cannot be used as a revenue run rate')
    return {'monthly_revenue':revenue,'kind':'historical_observed_mean','start':start,'end':end,
        'provider_keys':sorted(keys),'observed_provider_months':len(totals),
        'missing_provider_months':len(keys)*len(months)-len(totals),
        'observations':[{'provider_key':provider,'month':month,'revenue':amount}
                        for (provider,month),amount in sorted(totals.items())],
        'limitations':'Mean observed revenue per provider-month. Months without revenue records are excluded, not imputed as zero. Completeness, FTE, specialty, maturity and collections timing are not verified. Applying this baseline to a new hire is an assumption.'}


@dataclass(frozen=True)
class StaffGroup:
    hire: Hire
    start_month: int
    revenue_mode: str
    def __post_init__(self):
        if type(self.start_month) is not int or not 1<=self.start_month<=120: raise ValueError('Invalid staff start month')
        if self.revenue_mode not in {'included_in_clinic_baseline','incremental','none'}: raise ValueError('Invalid staff revenue mode')
        if self.revenue_mode!='incremental' and self.hire.monthly_revenue!=ZERO:
            raise ValueError('Revenue already included in the clinic baseline must not be added again')

@dataclass(frozen=True)
class ClinicCost:
    label: str
    monthly_amount: Decimal
    one_time_amount: Decimal
    start_month: int
    end_month: int
    monthly_amounts: dict[int,Decimal] = field(default_factory=dict)
    def __post_init__(self):
        if not self.label.strip() or type(self.start_month) is not int or type(self.end_month) is not int or not 1<=self.start_month<=self.end_month<=120: raise ValueError('Invalid clinic cost schedule')
        for value in (self.monthly_amount,self.one_time_amount): decimal_between(value,ZERO,Decimal('1000000000000'))
        for month,value in self.monthly_amounts.items():
            if type(month) is not int or not self.start_month<=month<=self.end_month: raise ValueError('Monthly cost override is outside its schedule')
            decimal_between(value,ZERO,Decimal('1000000000000'))

@dataclass(frozen=True)
class ClinicPlan:
    start_date: date
    months: int
    currency: str
    existing_monthly_revenue: Decimal
    existing_revenue_basis: str
    staff: tuple[StaffGroup,...]
    clinic_costs: tuple[ClinicCost,...]
    existing_revenue_by_month: dict[int,Decimal] = field(default_factory=dict)
    variable_cost_pct: Decimal = ZERO
    def __post_init__(self):
        if type(self.start_date) is not date or not 1900<=self.start_date.year<=2189 or type(self.months) is not int or not 1<=self.months<=120: raise ValueError('Invalid plan timeline')
        if len(self.currency)!=3 or not self.currency.isascii() or not self.currency.isupper() or not self.currency.isalpha(): raise ValueError('Invalid currency')
        decimal_between(self.existing_monthly_revenue,ZERO,Decimal('1000000000000'))
        decimal_between(self.variable_cost_pct,ZERO,HUNDRED)
        for month,value in self.existing_revenue_by_month.items():
            if type(month) is not int or not 1<=month<=self.months: raise ValueError('Revenue override is outside the plan horizon')
            decimal_between(value,ZERO,Decimal('1000000000000'))
        if not self.existing_revenue_basis.strip(): raise ValueError('Existing revenue basis is required, including explicit zero for a new clinic')
        if len(self.staff)>30 or len(self.clinic_costs)>50: raise ValueError('Plan exceeds supported line count')
        for group in self.staff:
            if group.start_month+group.hire.months-1>self.months: raise ValueError('Staff duration exceeds plan')
            if group.hire.start_date!=anniversary(self.start_date,group.start_month-1) or group.hire.currency!=self.currency: raise ValueError('Staff must use plan period boundaries and currency')
        if any(cost.end_month>self.months for cost in self.clinic_costs): raise ValueError('Clinic cost exceeds plan horizon')

@exact
def project_clinic(plan,scenario):
    projected=[project(group.hire,scenario) for group in plan.staff]
    periods=[]; cumulative_revenue=ZERO; cumulative_cost=ZERO; peak=ZERO; first=None
    for month in range(1,plan.months+1):
        existing=plan.existing_revenue_by_month.get(month,plan.existing_monthly_revenue)*scenario.revenue_multiplier
        staff_details=[]; revenue=existing; staff_cost=ZERO; upfront=ZERO
        for group,result in zip(plan.staff,projected):
            index=month-group.start_month
            if not 0<=index<group.hire.months: continue
            entry=result['periods'][index]
            staff_details.append({key:entry[key] for key in ('revenue','salary','benefits','payroll_taxes','malpractice','other_fixed_cost','variable_cost','onboarding_cost','total_cost')} |
                                 {'role_type':group.hire.role_type,'headcount':group.hire.headcount})
            revenue+=entry['revenue']; staff_cost+=entry['total_cost']; upfront+=entry['onboarding_cost']
        cost_details=[]; operating=ZERO
        for cost in plan.clinic_costs:
            if not cost.start_month<=month<=cost.end_month: continue
            recurring=cost.monthly_amounts.get(month,cost.monthly_amount)*scenario.fixed_cost_multiplier
            once=cost.one_time_amount if month==cost.start_month else ZERO
            operating+=recurring+once; upfront+=once
            cost_details.append({'label':cost.label,'recurring':recurring,'one_time':once,'total':recurring+once})
        # Upfront costs occur before this period's modeled revenue. Existing
        # cumulative surplus can fund them; do not double-count their period cost.
        peak=max(peak,cumulative_cost-cumulative_revenue+upfront)
        # Clinic variable rate applies only to baseline/driver revenue. New hires have
        # their own variable rates, so their revenue is not charged twice.
        clinic_variable=existing*plan.variable_cost_pct/HUNDRED
        operating+=clinic_variable
        cost_details.append({'label':'Revenue-linked costs','recurring':clinic_variable,'one_time':ZERO,'total':clinic_variable})
        total_cost=staff_cost+operating
        cumulative_revenue+=revenue; cumulative_cost+=total_cost
        balance=cumulative_revenue-cumulative_cost; peak=max(peak,-balance)
        ending=anniversary(plan.start_date,month)-timedelta(days=1)
        if first is None and balance>=ZERO: first={'month':month,'period_end':ending}
        periods.append({'month':month,'start':anniversary(plan.start_date,month-1),'end':ending,
            'existing_revenue':existing,'revenue':revenue,'staff_cost':staff_cost,'clinic_cost':operating,
            'total_cost':total_cost,'net':revenue-total_cost,'margin_pct':(revenue-total_cost)*HUNDRED/revenue if revenue>ZERO else None,'cumulative_revenue':cumulative_revenue,
            'cumulative_cost':cumulative_cost,'cumulative_net':balance,'staff':staff_details,'clinic_costs':cost_details})
    sustained=None
    for item in reversed(periods):
        if item['cumulative_net']<ZERO: break
        sustained={'month':item['month'],'period_end':item['end']}
    breakdown={label:sum((entry[key] for period in periods for entry in period['staff']),ZERO)
        for key,label in [('salary','Staff: salary'),('benefits','Staff: benefits'),('payroll_taxes','Staff: payroll taxes'),
            ('malpractice','Staff: malpractice'),('other_fixed_cost','Staff: other fixed costs'),
            ('variable_cost','Staff: variable costs'),('onboarding_cost','Staff: onboarding')]}
    for period in periods:
        for entry in period['clinic_costs']:
            label='Clinic: '+entry['label']
            breakdown[label]=breakdown.get(label,ZERO)+entry['total']
    return {'scenario':scenario.name,'assumptions':{'plan':asdict(plan),'scenario':asdict(scenario),
        'scope':'Whole-clinic budget for entered revenue and costs; not an automatically reconciled accounting ledger.',
        'revenue_rule':'Existing clinic revenue is entered once. Staff revenue is added only for incremental groups; existing staff revenue must be zero in staff lines.',
        'cost_rule':'All entered staff and operating costs are additive. Imported historical expenses are not added automatically. Avoid including payroll taxes, benefits or overhead twice.',
        'variable_cost_rule':'The clinic variable percentage applies only to existing/driver revenue. Incremental staff revenue uses its own variable percentage. All entered percentages are additional costs; exclude amounts already in fixed/recorded cost rows.',
        'timing':'Hire-relative monthly plan periods, no daily proration. New groups start at plan boundaries. Onboarding/one-time costs occur at the start of their specified period; other activity at period close.',
        'multiplier_rule':'Revenue multiplier applies to existing and incremental revenue. Fixed-cost multiplier applies to staff recurring costs and clinic monthly costs; it does not scale one-time charges or revenue-based variable cost rates.',
        'tax_rule':'Per-group effective payroll-tax percentages of base salary; no automatic jurisdiction rates, caps, wage thresholds or legal tax calculations.',
        'ramp_rule':'Scenario ramp is an assumption, not a hiring-history calibration, and applies by month since each incremental group starts. It does not ramp existing clinic revenue.',
        'break_even_rule':'First nonnegative cumulative period close; sustained break-even is only within the modeled horizon. Upfront/closing deficits do not capture all intra-period cash needs.',
        'staff_assumptions':[r['assumptions'] for r in projected]},'periods':periods,
        'summary':{'total_revenue':cumulative_revenue,'total_cost':cumulative_cost,'net':cumulative_revenue-cumulative_cost,
            'margin_pct':(cumulative_revenue-cumulative_cost)*HUNDRED/cumulative_revenue if cumulative_revenue>ZERO else None,
            'staff_cost':sum((p['staff_cost'] for p in periods),ZERO),'clinic_cost':sum((p['clinic_cost'] for p in periods),ZERO),
            'cost_breakdown':[{'label':label,'amount':amount} for label,amount in breakdown.items()],
            'first_break_even':first,'sustained_break_even_within_horizon':sustained,'peak_modeled_deficit':max(ZERO,peak),
            'break_even_status':'no_costs' if cumulative_cost==ZERO else ('reached' if first else 'not_reached_within_horizon')},
        'hiring_results':[{'role_type':g.hire.role_type,'start_month':g.start_month,**r['summary']} for g,r in zip(plan.staff,projected) if g.revenue_mode=='incremental']}

@exact
def clinic_sensitivity(plan,scenarios):
    if len(scenarios)!=3 or {s.name for s in scenarios}!={'pessimistic','expected','optimistic'}: raise ValueError('Supply exactly three named scenarios')
    ordered={s.name:s for s in scenarios}
    outputs=[project_clinic(plan,ordered[name]) for name in ('pessimistic','expected','optimistic')]
    proper=outputs[0]['summary']['net']<=outputs[1]['summary']['net']<=outputs[2]['summary']['net']
    return {'scenarios':outputs,'ordering_note':None if proper else 'Scenario final results do not follow their pessimistic/expected/optimistic labels; review the assumptions.'}
