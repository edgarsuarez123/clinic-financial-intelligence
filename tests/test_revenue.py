from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.analytics.revenue import revenue_report
from app.analytics.config import AnalyticsConfig
from app.main import create_app
from app.settings import Settings
from test_api import MemoryStore,login

START=date(2026,1,1);END=date(2026,6,30)
def rows():
    return [dict(full_date=date(2026,month,5),amount=Decimal(amount),medical_insurance=insurer,
        billing_code=code,category='Collections',category_key='private-category',currency='USD')
        for month,amount,insurer,code in [(1,'0.10','Demo A','C1'),(2,'0.20','Demo B','C2'),
            (3,'10.00','Demo A','C2'),(4,'-1.00','Demo A','C1'),(6,'2.00',None,None)]]

def test_quarters_exact_reconciliation_and_unclassified():
    r=revenue_report(rows(),START,END,'quarter')
    assert [p['revenue'] for p in r['periods']]==[Decimal('10.30'),Decimal('1.00')]
    assert r['total_revenue']==Decimal('11.30')
    for breakdown in r['breakdowns'].values():
        assert sum(x['revenue'] for x in breakdown)==r['total_revenue']
    assert '' in r['options']['medical_insurance']

def test_filters_intersect_and_unknown_periods_stay_missing():
    r=revenue_report(rows(),START,END,'month',{'medical_insurance':'Demo A','billing_code':'C1'})
    assert r['total_revenue']==Decimal('-0.90') and r['row_count']==2
    assert r['periods'][1]['revenue'] is None
    assert 'Demo B' in r['options']['medical_insurance']
    assert revenue_report(rows(),START,END,filters={'medical_insurance':''})['total_revenue']==Decimal('2.00')
    assert revenue_report(rows(),START,END,filters={'medical_insurance':'Absent'})['total_revenue'] is None

def test_week_partial_quarter_year_boundary_and_zero():
    r=revenue_report(rows(),date(2026,1,5),date(2026,1,6),'week')
    assert r['periods'][0]['partial'] and r['periods'][0]['period_start']==date(2026,1,5)
    r=revenue_report([],date(2025,12,1),date(2026,1,1),'quarter')
    assert [p['period_start'] for p in r['periods']]==[date(2025,10,1),date(2026,1,1)]
    zero=[{**rows()[0],'amount':Decimal('0.00')}]
    assert revenue_report(zero,START,END)['total_revenue']==Decimal('0.00')
    with pytest.raises(ValueError): revenue_report([],START,END,'day')

def test_revenue_api_authorization_and_filters():
    class Repo:
        calls=0
        def revenue_rows(self,*args): self.calls+=1; return rows(),'USD'
    store=MemoryStore();repo=Repo();cfg=AnalyticsConfig(authorized_user_ids=[store.user['user_id']])
    url='/api/v1/analytics/revenue?start=2026-01-01&end=2026-06-30&frequency=quarter&medical_insurance=Demo%20A'
    with TestClient(create_app(Settings('postgresql://unused'),store,analytics_config=cfg,analytics_repo=repo)) as client:
        assert client.get(url).status_code==401 and repo.calls==0
        _,headers=login(client)
        response=client.get(url,headers=headers)
        assert response.status_code==200 and response.json()['total_revenue']=='9.10'
        assert 'private-category' not in response.text
        assert response.json()['options']['category']==['Other revenue']
        assert client.get(url.replace('quarter','day'),headers=headers).status_code==422
        cfg.authorized_user_ids=[]
        assert client.get(url,headers=headers).status_code==403
