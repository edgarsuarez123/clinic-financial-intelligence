"""Execute only against a disposable migrated PostgreSQL database."""
from uuid import uuid4
from datetime import date
import psycopg
import pytest
from app.query.chat_repository import ConversationRepository
from app.query.chat_schemas import ConversationCreate,Context,Turn
from app.simulation.repository import BudgetMissing,BudgetConflict
from app.settings import Settings
from test_postgres import db
from test_budgets_postgres import budget_db
from test_query_postgres import query_db

pytestmark=pytest.mark.integration

@pytest.fixture
def chat_db(db):
    actor=uuid4()
    with psycopg.connect(db[0]) as c:c.execute('INSERT INTO core.app_user(user_id,username,password_hash) VALUES(%s,%s,%s)',(actor,str(actor),'synthetic'))
    repo=ConversationRepository(Settings(db[1]));key=uuid4();repo.create(ConversationCreate(conversation_id=key),actor,uuid4())
    return repo,actor,key

def test_conversation_durability_idempotency_lock_and_permission_revocation(db,chat_db):
    repo,actor,key=chat_db
    body=Turn(turn_id=uuid4(),expected_revision=1,question='Monthly trends',context=Context(start=date(2026,1,1),end=date(2026,1,31)))
    previous,attempt=repo.begin(key,body,actor,uuid4(),False,True)
    assert previous is None
    with pytest.raises(BudgetConflict):repo.begin(key,body,actor,uuid4(),False,True)
    repo.finish(key,body.turn_id,attempt,actor,uuid4(),{'status':'answered','answer':'Synthetic result','tables':[]},False,True)
    reopened=ConversationRepository(Settings(db[1])).get(key,actor,uuid4(),False,True)
    assert reopened['revision']==2 and len(reopened['turns'])==1
    assert repo.begin(key,body,actor,uuid4(),False,True)[0]['response']['answer']=='Synthetic result'
    with pytest.raises(BudgetMissing):repo.get(key,uuid4(),uuid4(),True,True)
    repo.protect(key,actor,uuid4(),True,True)
    with pytest.raises(BudgetMissing):repo.get(key,actor,uuid4(),False,True)
    assert repo.list(actor,uuid4(),False,True)['conversations']==[]

def test_expired_attempt_cannot_overwrite_retry_or_deleted_thread(db,chat_db):
    repo,actor,key=chat_db;rid=uuid4()
    body=Turn(turn_id=uuid4(),expected_revision=1,question='Monthly trends',context=Context(start=date(2026,1,1),end=date(2026,1,31)))
    _,first=repo.begin(key,body,actor,rid,True,True)
    with psycopg.connect(db[0]) as c:c.execute("UPDATE core.conversation_turn SET started_at=now()-interval '7 minutes' WHERE turn_id=%s",(body.turn_id,))
    _,second=repo.begin(key,body,actor,rid,True,True)
    with pytest.raises(BudgetConflict):repo.finish(key,body.turn_id,first,actor,rid,{'status':'answered'},False,False)
    repo.change(key,actor,rid,True,True,2,delete=True)
    with pytest.raises(BudgetMissing):repo.finish(key,body.turn_id,second,actor,rid,{'status':'answered'},False,False)
    with psycopg.connect(db[0]) as c:assert c.execute('SELECT count(*) FROM core.conversation_turn WHERE turn_id=%s',(body.turn_id,)).fetchone()[0]==1

def test_delete_restore_budget_revisions_and_audit_rollback(db,budget_db,monkeypatch):
    repo,actor,plan,result=budget_db;key=uuid4();repo.save(key,actor,uuid4(),'Plan',plan,result,False)
    deleted=repo.set_deleted(key,actor,uuid4(),False,1,True)
    assert deleted['revision']==2 and repo.list(actor,uuid4(),False)['budgets']==[]
    assert repo.deleted(actor,uuid4(),False)['budgets'][0]['budget_id']==key
    restored=repo.set_deleted(key,actor,uuid4(),False,2,False)
    assert restored['revision']==3 and restored['plan']==plan
    with pytest.raises(BudgetConflict):repo.set_deleted(key,actor,uuid4(),False,1,True)
    def fail(*args):raise RuntimeError('audit unavailable')
    monkeypatch.setattr(repo,'_audit',fail)
    with pytest.raises(RuntimeError):repo.set_deleted(key,actor,uuid4(),False,3,True)
    with psycopg.connect(db[0]) as c:assert c.execute('SELECT deleted_at,revision FROM core.saved_budget WHERE budget_id=%s',(key,)).fetchone()==(None,3)

def test_chat_aggregate_statements_and_private_storage_boundary(query_db):
    from app.query.executor import ReadOnlyExecutor
    from app.query.chat_catalog import CHAT_CATALOG
    executor=ReadOnlyExecutor(query_db)
    for query in CHAT_CATALOG.values():
        assert executor.execute_chat(query,{'start':date(1901,1,1),'end':date(1901,1,31),'clinic_location':None},executor.revision())==[]
    for name in ['core.conversation','core.conversation_turn']:
        with pytest.raises(psycopg.errors.InsufficientPrivilege),psycopg.connect(query_db) as c:c.execute('SELECT * FROM '+name)
