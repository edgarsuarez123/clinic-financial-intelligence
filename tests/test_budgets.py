from copy import deepcopy
from uuid import uuid4
from datetime import datetime,timezone
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.simulation.config import SimulationConfig
from app.simulation.repository import BudgetMissing,BudgetConflict,input_hash,visible
from app.analytics.config import AnalyticsConfig
from test_api import MemoryStore,login
from test_simulation import payload

class MemoryBudgets:
    """Repository contract double; real persistence/transactions tested separately in PostgreSQL."""
    def __init__(self,store): self.rows={}; self.store=store
    def list(self,actor,rid,provider_access,offset=0):
        self.store.audit(actor,'budget.list','budgets',rid)
        rows=[deepcopy(r) for r in self.rows.values() if visible(r,actor,provider_access)]
        return {'budgets':rows[offset:offset+50],'has_more':len(rows)>offset+50}
    def get(self,key,actor,rid,provider_access):
        row=self.rows.get(str(key))
        self.store.audit(actor,'budget.read',str(key),rid)
        if not visible(row,actor,provider_access): raise BudgetMissing()
        return deepcopy(row)
    def save(self,key,actor,rid,name,plan,result,provider_access,expected_revision=None):
        key=str(key);old=self.rows.get(key);digest=input_hash(name,plan)
        if old:
            if not visible(old,actor,provider_access): raise BudgetMissing()
            if expected_revision is None:
                if old['revision']==1 and old['input_hash']==digest: return deepcopy(old)
                raise BudgetConflict()
            if expected_revision!=old['revision']:
                if old['revision']==expected_revision+1 and old['input_hash']==digest: return deepcopy(old)
                raise BudgetConflict()
        elif expected_revision is not None: raise BudgetMissing()
        self.store.audit(actor,'budget.save',key,rid)
        now=datetime.now(timezone.utc)
        row={'budget_id':key,'owner_id':str(actor),'name':name,'plan':deepcopy(plan),'result':deepcopy(result),
             'revision':1 if old is None else old['revision']+1,'input_hash':digest,'deleted_at':None,
             'requires_provider_access':any(s['revenue']['kind']=='historical' for s in plan['staff']),
             'model_version':'clinic-budget-1','created_at':old['created_at'] if old else now,'updated_at':now}
        self.rows[key]=row
        return deepcopy(row)

def make_app(store,repo,access=None):
    return create_app(Settings('postgresql://unused'),store,budget_repo=repo,
        simulation_config=SimulationConfig(authorized_user_ids=[store.user['user_id']]),analytics_config=access)

def create_body(): return {'budget_id':str(uuid4()),'name':'Current clinic','plan':payload()}

def test_save_reopen_new_session_new_app_and_duplicate():
    store=MemoryStore(); repo=MemoryBudgets(store); body=create_body()
    with TestClient(make_app(store,repo)) as client:
        _,headers=login(client)
        saved=client.post('/api/v1/simulations/budgets',headers=headers,json=body)
        assert saved.status_code==200,saved.text
        assert 'owner_id' not in saved.json()
        assert client.post('/api/v1/simulations/budgets',headers=headers,json=body).json()==saved.json()
        client.post('/api/v1/auth/logout',headers=headers)
    with TestClient(make_app(store,repo)) as client:
        _,headers=login(client)
        reopened=client.get('/api/v1/simulations/budgets/'+body['budget_id'],headers=headers)
        assert reopened.json()==saved.json()
        assert len(client.get('/api/v1/simulations/budgets',headers=headers).json()['budgets'])==1
        duplicate=deepcopy(body);duplicate['budget_id']=str(uuid4());duplicate['name']='Higher rent'
        duplicate['plan']['clinic_costs'][0]['monthly_amount']='3000'
        assert client.post('/api/v1/simulations/budgets',headers=headers,json=duplicate).status_code==200
        assert repo.rows[body['budget_id']]['plan']['clinic_costs'][0]['monthly_amount']=='2000'
        assert len(repo.rows)==2

def test_update_revision_conflict_and_exact_retry():
    store=MemoryStore();repo=MemoryBudgets(store);body=create_body()
    with TestClient(make_app(store,repo)) as client:
        _,h=login(client); client.post('/api/v1/simulations/budgets',headers=h,json=body)
        update={'name':'Revised','plan':payload(),'expected_revision':1}
        url='/api/v1/simulations/budgets/'+body['budget_id']
        first=client.put(url,headers=h,json=update)
        assert first.status_code==200 and first.json()['revision']==2
        assert client.put(url,headers=h,json=update).json()==first.json()
        update['name']='Conflicting tab'
        r=client.put(url,headers=h,json=update)
        assert r.status_code==409 and r.json()['error']['code']=='budget_conflict'
        assert repo.rows[body['budget_id']]['name']=='Revised'
        assert client.post('/api/v1/simulations/budgets',headers=h,json=body).status_code==409

def test_access_revocation_ownership_audit_failure_and_invalid_plan():
    store=MemoryStore(); repo=MemoryBudgets(store); body=create_body()
    with TestClient(make_app(store,repo),raise_server_exceptions=False) as client:
        _,h=login(client)
        assert client.get('/api/v1/simulations/budgets').status_code==401
        assert client.post('/api/v1/simulations/budgets',headers=h,json=body).status_code==200
        key=body['budget_id']; url='/api/v1/simulations/budgets/'+key
        repo.rows[key]['requires_provider_access']=True
        assert client.get(url,headers=h).status_code==404
        assert client.get('/api/v1/simulations/budgets',headers=h).json()['budgets']==[]
        repo.rows[key]['requires_provider_access']=False
        repo.rows[key]['owner_id']=str(uuid4())
        assert client.get(url,headers=h).status_code==404
        assert client.put(url,headers=h,json={'name':'No','plan':payload(),'expected_revision':1}).status_code==404
        bad=create_body();bad['plan']['scenarios'][0]['ramp'][0]['productivity']='2'
        assert client.post('/api/v1/simulations/budgets',headers=h,json=bad).status_code==422
        assert store.events[-1][-1]=='error'
        store.audit_failure=True;new=create_body()
        assert client.post('/api/v1/simulations/budgets',headers=h,json=new).status_code==500
        assert new['budget_id'] not in repo.rows
