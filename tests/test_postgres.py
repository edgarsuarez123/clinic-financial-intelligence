"""Requires disposable PostgreSQL provisioned by infra/init-db.sh; never run on clinic data."""
import os
import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg.conninfo import make_conninfo
from fastapi.testclient import TestClient
from app.migrate import migrate, ROOT
from app.security import hash_password
from app.settings import Settings
from app.store import Store
from app.main import create_app

pytestmark=pytest.mark.integration

@pytest.fixture(scope="module")
def db():
    owner=os.getenv("TEST_MIGRATION_DATABASE_URL")
    app=os.getenv("TEST_DATABASE_URL")
    if not owner or not app:
        pytest.skip("Disposable PostgreSQL DSNs not configured")
    migrate(owner)
    return owner,app

@pytest.fixture
def fact(db):
    with psycopg.connect(db[0]) as c:
        uid=uuid4(); upload=uuid4(); category=uuid4(); tx=uuid4()
        c.execute("INSERT INTO core.app_user (user_id,username,password_hash) VALUES (%s,%s,%s)",(uid,str(uid),"test-placeholder"))
        c.execute("INSERT INTO core.uploads (upload_id,filename,uploaded_by,content_hash) VALUES (%s,'synthetic.csv',%s,%s)",(upload,uid,uuid4().hex+uuid4().hex))
        c.execute("INSERT INTO analytics.dim_date VALUES (20260908,'2026-09-08',37,'2026-09-07',2026,9,3,2026,2) ON CONFLICT DO NOTHING")
        c.execute("INSERT INTO analytics.dim_category (category_key,category_name,category_type) VALUES (%s,%s,'revenue')",(category,str(category)))
        c.execute("INSERT INTO analytics.transactions (transaction_id,date_key,category_key,type,amount,source_upload_id) VALUES (%s,20260908,%s,'revenue',%s,%s)",(tx,category,Decimal('0.10'),upload))
    return tx,upload,category

def test_migrations_repeat_without_change(db):
    migrate(db[0])
    with psycopg.connect(db[0]) as c:
        assert c.execute("SELECT count(*) FROM migrations.applied").fetchone()[0] == len(list(ROOT.glob('*.sql')))

def test_migration_tampering_rejected(db,tmp_path):
    for f in ROOT.glob('*.sql'): shutil.copy(f,tmp_path/f.name)
    f=sorted(tmp_path.glob('*.sql'))[0]
    f.write_text(f.read_text()+"\n-- changed")
    with pytest.raises(RuntimeError,match="has changed"): migrate(db[0],tmp_path)

def test_decimal_and_nullable_provider(db,fact):
    with psycopg.connect(db[0]) as c:
        row=c.execute("SELECT amount,provider_key FROM analytics.transactions WHERE transaction_id=%s",(fact[0],)).fetchone()
        assert row == (Decimal('0.10'),None)
        assert isinstance(row[0],Decimal)

@pytest.mark.parametrize("amount",[Decimal('0.001'),Decimal('NaN'),Decimal('Infinity')])
def test_invalid_currency_rejected(db,fact,amount):
    with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(db[0]) as c:
        c.execute("UPDATE analytics.transactions SET amount=%s WHERE transaction_id=%s",(amount,fact[0]))

def test_duplicate_upload_hash_rejected(db,fact):
    with pytest.raises(psycopg.errors.UniqueViolation), psycopg.connect(db[0]) as c:
        c.execute("INSERT INTO core.uploads (filename,uploaded_by,content_hash) SELECT filename,uploaded_by,content_hash FROM core.uploads WHERE upload_id=%s",(fact[1],))

def test_fact_requires_source(db,fact):
    with pytest.raises(psycopg.errors.NotNullViolation), psycopg.connect(db[0]) as c:
        c.execute("UPDATE analytics.transactions SET source_upload_id=NULL WHERE transaction_id=%s",(fact[0],))

def test_soft_delete_and_physical_delete_blocked(db,fact):
    with psycopg.connect(db[0]) as c:
        c.execute("UPDATE analytics.transactions SET deleted_at=now() WHERE transaction_id=%s",(fact[0],))
        assert c.execute("SELECT deleted_at IS NOT NULL FROM analytics.transactions WHERE transaction_id=%s",(fact[0],)).fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException), psycopg.connect(db[0]) as c:
        c.execute("DELETE FROM analytics.transactions WHERE transaction_id=%s",(fact[0],))

@pytest.mark.parametrize("statement",[
 "CREATE TABLE public.forbidden (id integer)",
 "SELECT * FROM analytics.transactions", "SELECT * FROM audit.audit_log",
 "UPDATE audit.audit_log SET action='tampered'", "DELETE FROM core.auth_session",
 "TRUNCATE core.auth_session",
])
def test_runtime_privilege_boundaries(db,statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(db[1]) as c:
        c.execute(statement)

def test_audit_append_and_owner_mutation_blocked(db):
    store=Store(Settings(db[1]))
    store.check_runtime()
    store.audit(None,"test.read","synthetic",uuid4())
    with pytest.raises(psycopg.errors.RaiseException), psycopg.connect(db[0]) as c:
        c.execute("UPDATE audit.audit_log SET action='tampered' WHERE target='synthetic'")

def test_real_auth_lifecycle(db):
    name=uuid4().hex
    with psycopg.connect(db[0]) as c:
        c.execute("INSERT INTO core.app_user (username,password_hash) VALUES (%s,%s)",(name,hash_password('synthetic-password-123')))
    with TestClient(create_app(Settings(db[1]))) as client:
        r=client.post('/api/v1/auth/login',json={'username':name,'password':'synthetic-password-123'})
        assert r.status_code == 200
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        assert client.get('/api/v1/auth/me',headers=headers).json()['username']==name
        assert client.get('/api/v1/health',headers=headers).status_code==200
        assert client.post('/api/v1/auth/logout',headers=headers).status_code==204
        assert client.get('/api/v1/auth/me',headers=headers).status_code==401

def test_shared_throttle(db):
    settings=Settings(db[1],login_limit=2)
    key=uuid4().hex
    assert Store(settings).login_allowed(key)
    assert Store(settings).login_allowed(key)
    assert not Store(settings).login_allowed(key)
