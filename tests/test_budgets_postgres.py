"""Real durability, transaction and privilege tests; disposable PostgreSQL only."""
from uuid import uuid4
from copy import deepcopy
import pytest
import psycopg
from psycopg.conninfo import make_conninfo
from app.settings import Settings
from app.simulation.repository import BudgetRepository,BudgetConflict,BudgetMissing
from app.simulation.schemas import PlanInput
from app.simulation.service import calculate
from app.analytics.routes import json_exact
from test_postgres import db
from test_simulation import payload

pytestmark=pytest.mark.integration

@pytest.fixture
def budget_db(db):
    actor=uuid4()
    with psycopg.connect(db[0]) as conn:
        conn.execute('INSERT INTO core.app_user (user_id,username,password_hash) VALUES (%s,%s,%s)',(actor,str(actor),'synthetic'))
    plan=PlanInput.model_validate(payload())
    result=json_exact(calculate(plan,None,actor,uuid4()))
    return BudgetRepository(Settings(db[1])),actor,plan.model_dump(mode='json'),result

def test_saved_budget_survives_repository_restart_and_retries(db,budget_db):
    repo,actor,plan,result=budget_db;key=uuid4()
    saved=repo.save(key,actor,uuid4(),'Clinic',plan,result,False)
    assert saved['revision']==1
    reopened=BudgetRepository(Settings(db[1])).get(key,actor,uuid4(),False)
    assert reopened['plan']==plan and reopened['result']==result
    assert isinstance(reopened['plan']['staff'][0]['annual_salary'],str)
    assert repo.save(key,actor,uuid4(),'Clinic',plan,result,False)['revision']==1
    changed=deepcopy(plan);changed['clinic_costs'][0]['monthly_amount']='3000'
    result2=json_exact(calculate(PlanInput.model_validate(changed),None,actor,uuid4()))
    assert repo.save(key,actor,uuid4(),'Revised',changed,result2,False,1)['revision']==2
    assert repo.save(key,actor,uuid4(),'Revised',changed,result2,False,1)['revision']==2
    with pytest.raises(BudgetConflict): repo.save(key,actor,uuid4(),'Stale',plan,result,False,1)
    assert repo.get(key,actor,uuid4(),False)['name']=='Revised'
    with pytest.raises(BudgetMissing): repo.get(key,uuid4(),uuid4(),False)
    assert repo.list(actor,uuid4(),False)['budgets'][0]['budget_id']==key
    with psycopg.connect(db[0]) as conn:
        assert conn.execute("SELECT count(*) FROM audit.audit_log WHERE target=%s AND action='budget.conflict'",(str(key),)).fetchone()[0]==1


def test_budget_save_rolls_back_when_audit_fails(db,budget_db,monkeypatch):
    repo,actor,plan,result=budget_db;key=uuid4()
    def fail(*args): raise RuntimeError('synthetic audit outage')
    monkeypatch.setattr(repo,'_audit',fail)
    with pytest.raises(RuntimeError): repo.save(key,actor,uuid4(),'Clinic',plan,result,False)
    with psycopg.connect(db[0]) as conn:
        assert conn.execute('SELECT count(*) FROM core.saved_budget WHERE budget_id=%s',(key,)).fetchone()[0]==0


def test_budget_soft_delete_and_privileges(db,budget_db):
    repo,actor,plan,result=budget_db;key=uuid4();repo.save(key,actor,uuid4(),'Clinic',plan,result,False)
    with pytest.raises(psycopg.errors.InsufficientPrivilege),psycopg.connect(db[1]) as conn:
        conn.execute('DELETE FROM core.saved_budget WHERE budget_id=%s',(key,))
    with pytest.raises(psycopg.errors.RaiseException),psycopg.connect(db[0]) as conn:
        conn.execute('DELETE FROM core.saved_budget WHERE budget_id=%s',(key,))
    with psycopg.connect(db[0]) as conn:
        assert conn.execute("SELECT has_table_privilege('clinic_query','core.saved_budget','SELECT')").fetchone()[0] is False
        conn.execute('UPDATE core.saved_budget SET deleted_at=now() WHERE budget_id=%s',(key,))
    with pytest.raises(BudgetMissing): repo.get(key,actor,uuid4(),False)


def test_historical_budget_hidden_when_permission_revoked(db,budget_db):
    repo,actor,plan,result=budget_db;key=uuid4()
    # Repository fixture tests access to a saved document; API validates/calculates historical inputs separately.
    plan['staff'][0]['revenue']['kind']='historical'
    repo.save(key,actor,uuid4(),'Historical',plan,result,True)
    assert repo.get(key,actor,uuid4(),True)['requires_provider_access']
    with pytest.raises(BudgetMissing): repo.get(key,actor,uuid4(),False)
    assert repo.list(actor,uuid4(),False)['budgets']==[]
