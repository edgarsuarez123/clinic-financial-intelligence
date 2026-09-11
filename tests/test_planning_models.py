from copy import deepcopy
from datetime import date
from decimal import Decimal,localcontext
import pytest
from app.simulation.schemas import PlanInput
from app.simulation.service import calculate
from app.simulation.forecast import forecast_months
from app.simulation.calculations import anniversary
from app.query.chat_tools import apply_changes
from app.query.chat_schemas import Change
from test_simulation import payload

def expected(plan): return next(s for s in calculate(PlanInput.model_validate(plan),None,None,None)['scenarios'] if s['scenario']=='expected')

def driver_plan():
    p=payload();p.update(months=3,staff=[],existing_monthly_revenue='999999',revenue_mode='drivers',variable_cost_pct='5',existing_revenue_by_month={},
        revenue_drivers=[{'insurance':'Synthetic payer','billing_code':'Synthetic code','monthly_units':'800','collected_per_unit':'100'}],
        clinic_costs=[{'label':'Payroll and overhead','monthly_amount':'60000','one_time_amount':'0','start_month':1,'end_month':3}])
    return p

def test_driver_worked_example_replaces_amount_not_added_and_sensitivity():
    p=driver_plan()
    for s in p['scenarios']:
        s['fixed_cost_multiplier']='1';s['revenue_multiplier']='1'
        s['volume_multiplier']={'expected':'1','pessimistic':'.9','optimistic':'1.1'}[s['name']]
        s['payment_multiplier']={'expected':'1','pessimistic':'.95','optimistic':'1.03'}[s['name']]
    result=calculate(PlanInput.model_validate(p),None,None,None)
    values={s['scenario']:s['periods'][0] for s in result['scenarios']}
    assert values['expected']['revenue']==Decimal('80000')
    assert values['expected']['net']==Decimal('16000')
    assert values['pessimistic']['net']==Decimal('4980')
    assert values['optimistic']['net']==Decimal('26108')
    assert values['expected']['margin_pct']==Decimal('20')

def test_month_specific_drivers_salary_and_no_duplicate_variable_charge():
    p=driver_plan();p['revenue_drivers'][0]['units_by_month']={'2':'900'}
    assert expected(p)['periods'][1]['revenue']==Decimal('90000')
    p=payload();p['staff'][0]['monthly_salary']={'2':'6000'}
    r=expected(p)
    second=r['periods'][1]['staff'][0]
    assert second['salary']==Decimal('6000')*p['staff'][0]['headcount']
    assert second['payroll_taxes']==second['salary']*Decimal(p['staff'][0]['payroll_tax_pct'])/100

def test_driver_mixed_modes_and_invalid_schedule_rejected():
    p=driver_plan();p['existing_revenue_by_month']={'1':'1'}
    with pytest.raises(ValueError,match='cannot be combined'): expected(p)
    p=driver_plan();p['revenue_drivers'][0]['units_by_month']={'4':'1'}
    with pytest.raises(ValueError,match='horizon'): expected(p)
    p=payload();p['staff'][0]['monthly_salary']={'120':'1'}
    with pytest.raises(ValueError,match='employment'): expected(p)

def test_what_if_draft_does_not_mutate_saved_plan_and_preserves_exact_cents():
    p=payload();original=deepcopy(p)
    draft=apply_changes(p,[Change(kind='cost_percent',row_index=0,from_month=2,through_month=2,percent='10')])
    assert p==original
    assert draft.clinic_costs[0].monthly_amounts=={2:Decimal('2200.00')}
    assert expected(draft.model_dump(mode='json'))['periods'][0]['clinic_cost']==expected(p)['periods'][0]['clinic_cost']
    with pytest.raises(ValueError,match='does not exist'): apply_changes(p,[Change(kind='salary_percent',row_index=29,percent='10')])

def history(n=48): return [{'period':anniversary(date(2020,1,1),i).isoformat(),'revenue':str(10000+i*100)} for i in range(n)]

def test_forecast_validates_chronologically_and_is_decimal():
    with localcontext() as ctx:
        ctx.prec=5
        r=forecast_months(history(),6,date(2026,1,1))
    assert r['method']=='linear_trend'
    assert r['periods'][0]['revenue']==Decimal('14800.00')
    assert r['validation_mae']==0
    assert all(p['lower_80']<=p['revenue']<=p['upper_80'] and p['validation_windows']>=8 for p in r['periods'])

@pytest.mark.parametrize('mode',['short','gap','negative','future','horizon'])
def test_forecast_refuses_unsupported_history(mode):
    rows=history();horizon=6;as_of=date(2026,1,1)
    if mode=='short': rows=rows[:6]
    if mode=='gap': rows.pop(2)
    if mode=='negative': rows[0]['revenue']='-1'
    if mode=='future': as_of=date(2021,1,15)
    if mode=='horizon': rows=rows[:24];horizon=12
    with pytest.raises(ValueError): forecast_months(rows,horizon,as_of)
