from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.analytics.calculations import Transaction
from app.analytics.config import AnalyticsConfig
from app.analytics.repository import DataUnavailable
from app.main import create_app
from app.settings import Settings
from test_api import MemoryStore,login

class Repository:
    def __init__(self):
        self.provider=str(uuid4()); self.category=str(uuid4()); self.reads=[]; self.fail=False
    def metadata(self,uid,rid):
        return {'first_date':date(2026,1,5),'last_date':date(2026,1,5),'row_count':2}
    def rows(self,uid,rid,start,end,providers=False):
        self.reads.append(providers)
        if self.fail: raise DataUnavailable('currency_unconfirmed','Currency needs confirmation.')
        return [Transaction(date(2026,1,5),Decimal('100.10'),'revenue','rev','revenue',self.provider if providers else None),
                Transaction(date(2026,1,5),Decimal('40.00'),'expense',self.category,'fixed_cost',self.provider if providers else None)],'USD'

@pytest.fixture
def api():
    store=MemoryStore(); repo=Repository()
    config=AnalyticsConfig(authorized_user_ids=[store.user['user_id']],provider_labels={repo.provider:'Private clinician'})
    with TestClient(create_app(Settings('postgresql://unused'),store,analytics_config=config,analytics_repo=repo)) as client:
        yield client,store,repo,config

URL='/api/v1/analytics/dashboard?start=2026-01-05&end=2026-01-11'

def test_dashboard_requires_authentication(api):
    client,_,repo,_=api
    assert client.get(URL).status_code==401 and not repo.reads

def test_decimal_values_stay_strings_and_provider_data_is_absent(api):
    client,_,repo,_=api; _,headers=login(client)
    r=client.get(URL,headers=headers)
    assert r.status_code==200
    from app.analytics.schemas import DashboardResponse
    DashboardResponse.model_validate(r.json())
    assert r.json()['summary']['revenue']=='100.10'
    assert r.json()['summary']['expense']=='40.00'
    assert repo.provider not in r.text and 'Private clinician' not in r.text
    assert repo.category not in r.text
    assert repo.reads==[False]

def test_provider_cost_access_is_checked_before_read(api):
    client,_,repo,_=api; _,headers=login(client)
    assert client.get(URL.replace('dashboard','providers'),headers=headers).status_code==403
    assert not repo.reads

def test_authorized_provider_response_preserves_unknown_costs(api):
    client,store,repo,config=api
    config.compensation_authorized_user_ids.append(store.user['user_id'])
    _,headers=login(client)
    r=client.get(URL.replace('dashboard','providers'),headers=headers)
    assert r.status_code==200
    row=r.json()['providers'][0]
    assert row['fully_loaded_cost'] is None and row['contribution'] is None
    assert row['label']=='Private clinician'
    assert repo.reads==[True]

def test_invalid_range_no_data_read(api):
    client,_,repo,_=api; _,headers=login(client)
    assert client.get('/api/v1/analytics/dashboard?start=2026-02-01&end=2026-01-01',headers=headers).status_code==422
    assert not repo.reads

def test_currency_failure_is_explicit(api):
    client,_,repo,_=api; repo.fail=True; _,headers=login(client)
    r=client.get(URL,headers=headers)
    assert r.status_code==422 and r.json()['error']['code']=='currency_unconfirmed'

def test_general_access_disabled_by_default():
    store=MemoryStore(); repo=Repository()
    with TestClient(create_app(Settings('postgresql://unused'),store,analytics_repo=repo)) as client:
        _,headers=login(client)
        assert client.get(URL,headers=headers).status_code==403
        assert not repo.reads

def test_provider_permission_cannot_exist_without_general_permission():
    with pytest.raises(ValueError): AnalyticsConfig(compensation_authorized_user_ids=[uuid4()])
