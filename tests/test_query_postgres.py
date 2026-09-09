"""The read-only database role must enforce privileges even with READ WRITE selected."""
import os
from datetime import date
from decimal import Decimal
from uuid import uuid4
import psycopg
import pytest
from app.query.executor import ReadOnlyExecutor
from app.query.catalog import CATALOG,Unreliable
from app.query.repository import QueryRepository
from app.settings import Settings
from app.query.provider import Completion
from test_query import config
from test_postgres import db

pytestmark=pytest.mark.integration

@pytest.fixture(scope='module')
def query_db(db):
    dsn=os.getenv('TEST_QUERY_DATABASE_URL')
    if not dsn: pytest.skip('Disposable clinic_query DSN is not configured')
    return dsn

@pytest.mark.parametrize('statement',[
 "INSERT INTO analytics.transactions DEFAULT VALUES",'UPDATE analytics.transactions SET amount=0',
 'DELETE FROM analytics.transactions','CREATE TABLE analytics.forbidden (id integer)',
 'CREATE TABLE public.forbidden (id integer)','SELECT * FROM core.saved_budget',
 'SELECT * FROM core.app_user','SELECT * FROM core.query_log','SELECT * FROM analytics.transactions',
 "SET ROLE clinic_migrator",
])
def test_query_role_cannot_write_or_read_unapproved_tables(query_db,statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege),psycopg.connect(query_db) as c:
        c.execute('SET TRANSACTION READ WRITE')
        c.execute(statement)


def test_executor_rejects_application_role(db):
    with pytest.raises(Unreliable): ReadOnlyExecutor(db[1]).revision()


def test_all_catalog_statements_execute_under_query_role(query_db):
    executor=ReadOnlyExecutor(query_db)
    for query in CATALOG.values():
        rows=executor.execute(query,{'start':date(1901,1,1),'end':date(1901,1,31)},executor.revision())
        assert isinstance(rows,list)


def test_data_revision_changes_on_committed_financial_change(db,query_db):
    executor=ReadOnlyExecutor(query_db);before=executor.revision()
    with psycopg.connect(db[0]) as conn:
        conn.execute('UPDATE analytics.dim_category SET category_name=category_name WHERE false')
    assert executor.revision()>before
    with pytest.raises(Unreliable): executor.execute(CATALOG['summary'],{'start':date(1901,1,1),'end':date(1901,1,31)},before)


def test_query_rate_usage_cache_and_audit_transactions(db,monkeypatch):
    uid=uuid4();repo=QueryRepository(Settings(db[1]));cfg=config(requests_per_window=1)
    with psycopg.connect(db[0]) as conn:
        conn.execute('INSERT INTO core.app_user(user_id,username,password_hash) VALUES(%s,%s,%s)',(uid,str(uid),'synthetic'))
        conn.execute('UPDATE core.nl_rate_limit SET attempts=0,window_start=now() WHERE singleton')
    key,allowed=repo.begin(uid,uuid4(),'Synthetic question',cfg)
    assert allowed
    assert repo.begin(uid,uuid4(),'Synthetic second question',cfg)[1] is False
    repo.usage(key,uid,uuid4(),'translate',Completion('{}',100,20,'test-model'))
    repo.usage(key,uid,uuid4(),'explain',None)
    cachekey=uuid4().hex+uuid4().hex;response={'answer':'Synthetic'}
    repo.finish(key,uid,uuid4(),'answered','SELECT reviewed',{'start':'1901-01-01'},response,cachekey,300)
    assert repo.cache(cachekey,uid,uuid4())==response
    assert repo.cache(cachekey,uuid4(),uuid4()) is None
    with psycopg.connect(db[0]) as conn:
        row=conn.execute('SELECT input_tokens,output_tokens,token_cost,unknown_usage_calls FROM core.query_log WHERE query_id=%s',(key,)).fetchone()
        assert row==(100,20,Decimal('0.00014'),1)
        before=conn.execute('SELECT count(*) FROM core.query_log').fetchone()[0]
    def fail(*args): raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(repo,'_audit',fail)
    with pytest.raises(RuntimeError): repo.begin(uid,uuid4(),'Must roll back',cfg)
    with psycopg.connect(db[0]) as conn:
        assert conn.execute('SELECT count(*) FROM core.query_log').fetchone()[0]==before


def test_real_database_performs_exact_financial_arithmetic(db,query_db):
    from datetime import timedelta
    actor=uuid4();upload=uuid4();revenue=uuid4();cost=uuid4();day=date(1902,1,6);iso=day.isocalendar()
    with psycopg.connect(db[0]) as c:
        c.execute('INSERT INTO core.app_user(user_id,username,password_hash) VALUES(%s,%s,%s)',(actor,str(actor),'synthetic'))
        c.execute('''INSERT INTO core.uploads(upload_id,filename,uploaded_by,content_hash,status,currency,total_rows,rows_accepted)
            VALUES(%s,'synthetic-query.csv',%s,%s,'completed','USD',2,2)''',(upload,actor,uuid4().hex+uuid4().hex))
        c.execute('INSERT INTO analytics.dim_date VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
            (19020106,day,iso.week,day-timedelta(days=day.weekday()),iso.year,day.month,1,day.year,iso.weekday))
        c.execute("INSERT INTO analytics.dim_category(category_key,category_name,category_type) VALUES(%s,%s,'revenue'),(%s,%s,'fixed_cost')",
            (revenue,str(revenue),cost,str(cost)))
        c.execute('''INSERT INTO analytics.transactions(date_key,category_key,type,amount,source_upload_id,source_row)
            VALUES(19020106,%s,'revenue',100.10,%s,1),(19020106,%s,'expense',25.10,%s,2)''',(revenue,upload,cost,upload))
    try:
        executor=ReadOnlyExecutor(query_db);params={'start':day,'end':day}
        rows=executor.execute(CATALOG['summary'],params,executor.revision())
        assert len(rows)==1
        assert (rows[0]['revenue'],rows[0]['expense'],rows[0]['net'])==(Decimal('100.10'),Decimal('25.10'),Decimal('75.00'))
        assert isinstance(rows[0]['net'],Decimal)
        costs=executor.execute(CATALOG['cost_breakdown'],params,executor.revision())
        assert costs[0]['fixed_cost']==Decimal('25.10') and costs[0]['variable_cost']==0
    finally:
        with psycopg.connect(db[0]) as c: c.execute('UPDATE core.uploads SET deleted_at=now() WHERE upload_id=%s',(upload,))
