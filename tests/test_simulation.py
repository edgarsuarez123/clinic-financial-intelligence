from dataclasses import replace
from datetime import date
from decimal import Decimal as D,localcontext
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.simulation.calculations import *
from app.simulation.config import SimulationConfig
from app.analytics.config import AnalyticsConfig
from app.analytics.calculations import Transaction
from app.main import create_app
from app.settings import Settings
from test_api import MemoryStore,login


def hire(**changes):
    return replace(Hire('Provider','direct_provider',date(2026,1,1),3,'USD',D('12000'),D('0'),D('0'),D('0'),D('1000'),D('0'),'Synthetic worked example',D('2000'),{'kind':'manual','basis':'Synthetic'},D('0'),1),**changes)
def scenario(name='expected',**changes):
    return replace(Scenario(name,D('1'),D('1'),(RampStep(1,D('.5')),RampStep(2,D('1'))),'Synthetic assumption'),**changes)
def payload(): return json.loads(Path('config/simulation-example.json').read_text())

def test_hand_computed_break_even():
    result=project(hire(),scenario())
    assert [p['cumulative_net'] for p in result['periods']]==[D('-1000'),D('0'),D('1000')]
    assert result['summary']['first_break_even']=={'month':2,'period_end':date(2026,2,28)}
    assert result['summary']['peak_modeled_deficit']==D('1000')
    assert result['assumptions']['payroll_tax_pct']==D('0')

def test_payroll_headcount_and_benefits():
    result=project(hire(annual_salary=D('60000'),headcount=2,payroll_tax_pct=D('10'),benefits_pct=D('20')),scenario())
    p=result['periods'][0]
    assert (p['salary'],p['payroll_taxes'],p['benefits'])==(D('10000'),D('1000'),D('2000'))
    assert p['onboarding_cost']==D('2000')

def test_decimal_context_independent_and_month_end():
    h=hire(start_date=date(2026,1,31),annual_salary=D('1'))
    expected=project(h,scenario())
    with localcontext() as c:
        c.prec=6
        assert project(h,scenario())==expected
    assert [p['start'] for p in expected['periods']]==[date(2026,1,31),date(2026,2,28),date(2026,3,31)]

@pytest.mark.parametrize('changes',[{'annual_salary':1.0},{'payroll_tax_pct':D('101')},{'headcount':0},{'benefits_pct':D('NaN')},{'months':0}])
def test_invalid_hire(changes):
    with pytest.raises(ValueError): hire(**changes)

def test_cost_only_and_crossing_that_reverses():
    assert project(hire(revenue_mechanism='none',monthly_revenue=D('0')),scenario())['summary']['first_break_even'] is None
    result=project(hire(onboarding_cost=D('0')),scenario(ramp=(RampStep(1,D('1')),RampStep(2,D('0')))))
    assert result['summary']['first_break_even']['month']==1
    assert result['summary']['sustained_break_even_within_horizon'] is None
    assert project(hire(annual_salary=D('0'),onboarding_cost=D('0')),scenario())['summary']['break_even_status']=='no_costs'

def test_ramp_validation_and_sensitivity():
    with pytest.raises(ValueError): scenario(ramp=(RampStep(2,D('1')),))
    with pytest.raises(ValueError): scenario(ramp=(RampStep(1,D('1')),RampStep(1,D('1'))))
    with pytest.raises(ValueError): sensitivity(hire(),[scenario()]*3)
    r=sensitivity(hire(),[scenario('pessimistic',revenue_multiplier=D('2')),scenario(),scenario('optimistic')])
    assert r['ordering_note']

def test_historical_sparse_and_partial_months():
    rows=[Transaction(date(2026,1,3),D('1000'),'revenue','r','revenue','a'),Transaction(date(2026,3,3),D('3000'),'revenue','r','revenue','a')]
    result=historical_baseline(rows,['a'],date(2026,1,1),date(2026,3,31))
    assert result['monthly_revenue']==D('2000') and result['missing_provider_months']==1
    assert historical_baseline(rows,['a'],date(2026,1,2),date(2026,3,31))['monthly_revenue']==D('3000')
    with pytest.raises(ValueError): historical_baseline(rows,['a','b'],date(2026,1,1),date(2026,3,31))
    with pytest.raises(ValueError): historical_baseline(rows,['a'],date(2026,1,1),date(2026,1,20))

def test_clinic_schedules_and_no_double_count():
    h=hire(months=2,annual_salary=D('60000'),headcount=2,benefits_pct=D('20'),payroll_tax_pct=D('10'),onboarding_cost=D('0'),monthly_revenue=D('0'),revenue_mechanism='none')
    plan=ClinicPlan(date(2026,1,1),3,'USD',D('20000'),'Synthetic', (StaffGroup(h,1,'included_in_clinic_baseline'),),
        (ClinicCost('Rent',D('2000'),D('5000'),1,3),ClinicCost('Utilities',D('300'),D('0'),1,3),ClinicCost('Software',D('200'),D('0'),1,3)))
    r=project_clinic(plan,scenario())
    assert [p['net'] for p in r['periods']]==[D('-500'),D('4500'),D('17500')]
    assert r['summary']['first_break_even']['month']==2
    assert sum(x['amount'] for x in r['summary']['cost_breakdown'])==r['summary']['total_cost']
    assert all(p['revenue']==D('20000') for p in r['periods'])
    with pytest.raises(ValueError): StaffGroup(hire(),1,'included_in_clinic_baseline')
    later=StaffGroup(replace(h,start_date=date(2026,2,1),months=1,headcount=1,payroll_tax_pct=D('5')),2,'none')
    second=project_clinic(replace(plan,staff=(later,)),scenario())['periods']
    assert second[0]['staff_cost']==D('0') and second[1]['staff'][0]['payroll_taxes']==D('250') and second[2]['staff_cost']==D('0')

def test_month_specific_revenue_costs_and_sensitivity():
    plan=ClinicPlan(date(2026,1,1),3,'USD',D('10000'),'Synthetic seasonal budget',(),
        (ClinicCost('Rent',D('2000'),D('500'),1,3,{2:D('3000'),3:D('0')}),),{2:D('15000'),3:D('0')})
    result=project_clinic(plan,scenario())
    assert [p['revenue'] for p in result['periods']]==[D('10000'),D('15000'),D('0')]
    assert [p['total_cost'] for p in result['periods']]==[D('2500'),D('3000'),D('0')]
    assert result['summary']['net']==D('19500')
    scaled=project_clinic(plan,scenario(revenue_multiplier=D('.8'),fixed_cost_multiplier=D('1.1')))
    assert scaled['periods'][1]['revenue']==D('12000')
    assert scaled['periods'][1]['total_cost']==D('3300')
    assert scaled['periods'][0]['total_cost']==D('2700')
    assert result['assumptions']['plan']['existing_revenue_by_month'][2]==D('15000')
    with pytest.raises(ValueError): replace(plan,existing_revenue_by_month={4:D('1')})
    with pytest.raises(ValueError): ClinicCost('Rent',D('1'),D('0'),2,3,{1:D('1')})

@pytest.fixture
def sim_api():
    store=MemoryStore(); config=SimulationConfig(authorized_user_ids=[store.user['user_id']])
    class Repo:
        calls=0
        def rows(self,*args,**kwargs): self.calls+=1; return [],'USD'
    repo=Repo()
    with TestClient(create_app(Settings('postgresql://unused'),store,simulation_config=config,analytics_repo=repo),raise_server_exceptions=False) as client:
        yield client,store,repo

def test_api_exact_repeat_and_assumptions(sim_api):
    client,store,repo=sim_api; _,headers=login(client)
    r=client.post('/api/v1/simulations/clinic',headers=headers,json=payload())
    assert r.status_code==200,r.text
    assert r.json()==client.post('/api/v1/simulations/clinic',headers=headers,json=payload()).json()
    expected=r.json()['scenarios'][1]
    assert isinstance(expected['periods'][0]['net'],str)
    assert D(expected['periods'][0]['net'])==D('-500')
    assert expected['assumptions']['plan']['staff'][0]['hire']['payroll_tax_pct']=='10'
    assert repo.calls==0
    assert any(e[1]=='simulation.calculate' for e in store.events)

def test_api_auth_float_invalid_and_history_denied(sim_api):
    client,store,repo=sim_api
    assert client.post('/api/v1/simulations/clinic',json=payload()).status_code==401
    _,headers=login(client)
    bad=payload();bad['staff'][0]['annual_salary']=60000.1
    assert client.post('/api/v1/simulations/clinic',headers=headers,json=bad).status_code==422
    bad=payload();bad['staff'][0]['revenue']={'kind':'historical','basis':'Test','provider_keys':[str(store.user['user_id'])],'start':'2026-01-01','end':'2026-02-28'}
    assert client.post('/api/v1/simulations/clinic',headers=headers,json=bad).status_code==403
    assert repo.calls==0
    bad=payload();bad['scenarios'][0]['ramp'][0]['productivity']='2'
    assert client.post('/api/v1/simulations/clinic',headers=headers,json=bad).status_code==422
    store.audit_failure=True
    assert client.post('/api/v1/simulations/clinic',headers=headers,json=payload()).status_code==500

def test_default_access_denied():
    store=MemoryStore()
    with TestClient(create_app(Settings('postgresql://unused'),store)) as client:
        _,headers=login(client)
        assert client.post('/api/v1/simulations/clinic',headers=headers,json=payload()).status_code==403

def test_authorized_historical_baseline_is_derived_by_server():
    store=MemoryStore(); uid=store.user['user_id']
    class Repo:
        def rows(self,*args,**kwargs):
            assert kwargs['providers'] is True
            return [Transaction(date(2026,1,1),D('9000'),'revenue','r','revenue',str(uid))],'USD'
    access=AnalyticsConfig(authorized_user_ids=[uid],compensation_authorized_user_ids=[uid])
    with TestClient(create_app(Settings('postgresql://unused'),store,simulation_config=SimulationConfig(authorized_user_ids=[uid]),analytics_config=access,analytics_repo=Repo())) as client:
        _,headers=login(client); body=payload()
        body['staff'][0]['revenue_mode']='incremental'
        body['staff'][0]['revenue']={'kind':'historical','provider_keys':[str(uid)],'start':'2026-01-01','end':'2026-01-31','basis':'Explicit comparable provider assumption'}
        response=client.post('/api/v1/simulations/clinic',headers=headers,json=body)
        assert response.status_code==200,response.text
        h=response.json()['scenarios'][1]['assumptions']['plan']['staff'][0]['hire']
        assert h['monthly_revenue']=='9000' and h['revenue_basis']['kind']=='historical_observed_mean'
        body['currency']='EUR'
        assert client.post('/api/v1/simulations/clinic',headers=headers,json=body).status_code==422
