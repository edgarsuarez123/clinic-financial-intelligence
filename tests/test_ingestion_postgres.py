import hashlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import pytest
import psycopg
from app.ingestion.repository import IngestionRepository, UploadConflict
from app.ingestion.config import Profile
from app.ingestion.validation import prepare
from app.settings import Settings
from test_postgres import db

pytestmark=pytest.mark.integration

@pytest.fixture
def ingest(db):
    uid,category,provider=uuid4(),uuid4(),uuid4()
    with psycopg.connect(db[0]) as c:
        c.execute("INSERT INTO core.app_user (user_id,username,password_hash) VALUES (%s,%s,'synthetic')",(uid,str(uid)))
        c.execute("INSERT INTO analytics.dim_category (category_key,category_name,category_type) VALUES (%s,%s,'revenue')",(category,str(category)))
        c.execute("INSERT INTO analytics.dim_provider (provider_key,name,role) VALUES (%s,'SYNTHETIC','demo')",(provider,))
    profile=Profile(columns={k:k for k in ('date','amount','type','category','provider')},date_format='%Y-%m-%d',
        types={'revenue':'revenue'},categories={'Collections':category},providers={'DEMO':provider},
        currency='USD',allow_negative_amounts=False)
    data=b'date,amount,type,category,provider\n2026-01-05,0.10,revenue,Collections,DEMO\n2026-01-06,no,revenue,Collections,DEMO\n'
    # Content-specific unique bytes without adding any out-of-schema value.
    data=data.replace(b'0.10',str(Decimal(int(uid.hex[:6],16))/Decimal(100)).encode())
    return IngestionRepository(Settings(db[1])),uid,profile,data

def enqueue(ingest):
    repo,uid,profile,data=ingest
    return repo.enqueue(uid,hashlib.sha256(data).hexdigest(),'csv','demo',profile,prepare(data,'csv',profile),uuid4())

def drain(repo):
    while repo.process_one(): pass

def test_identical_file_twice_preserves_fact_state(db,ingest):
    repo,uid,_,_=ingest
    first,duplicate=enqueue(ingest); assert not duplicate
    drain(repo)
    with psycopg.connect(db[0]) as c:
        before=c.execute('SELECT transaction_id,amount,source_row FROM analytics.transactions WHERE source_upload_id=%s',(first['upload_id'],)).fetchall()
    second,duplicate=enqueue(ingest); assert duplicate
    drain(repo)
    with psycopg.connect(db[0]) as c:
        after=c.execute('SELECT transaction_id,amount,source_row FROM analytics.transactions WHERE source_upload_id=%s',(first['upload_id'],)).fetchall()
    assert before==after and len(after)==1
    assert first['upload_id']==second['upload_id']
    summary=repo.summary(first['upload_id'],uid,uuid4())
    assert summary['status']=='completed'
    assert summary['rows_accepted']==1 and summary['rows_rejected']==1

def test_revenue_dimensions_survive_queue_worker_and_read_view(db,ingest):
    repo,uid,profile,data=ingest
    profile=Profile.model_validate({**profile.model_dump(),
        'columns':{**profile.columns,'medical_insurance':'medical_insurance','billing_code':'billing_code'},
        'medical_insurances':{'Demo A':'Demo A'},'billing_codes':{'C1':'C1'}})
    lines=data.decode().splitlines()
    payload=(lines[0]+',medical_insurance,billing_code\n'+lines[1]+',Demo A,C1\n').encode()
    row,_=repo.enqueue(uid,hashlib.sha256(payload).hexdigest(),'csv','revenue-demo',profile,prepare(payload,'csv',profile),uuid4())
    drain(repo)
    with psycopg.connect(db[0]) as c:
        actual=c.execute('SELECT medical_insurance,billing_code FROM analytics.transactions WHERE source_upload_id=%s',(row['upload_id'],)).fetchone()
        assert actual==('Demo A','C1')
    with repo.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM analytics.revenue_facts WHERE medical_insurance=%s AND billing_code=%s',('Demo A','C1')).fetchone()['n']>=1
    assert repo.summary(row['upload_id'],uid,uuid4())['status']=='completed'

def test_concurrent_same_file_and_workers(db,ingest):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:enqueue(ingest),range(2)))
    assert len({r[0]['upload_id'] for r in results})==1
    assert sum(r[1] for r in results)==1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:drain(ingest[0]),range(2)))
    with psycopg.connect(db[0]) as c:
        assert c.execute('SELECT count(*) FROM analytics.transactions WHERE source_upload_id=%s',(results[0][0]['upload_id'],)).fetchone()[0]==1

def test_savepoint_rolls_back_partial_failure_and_retry(db,ingest,monkeypatch):
    repo,uid,_,_=ingest; row,_=enqueue(ingest)
    original=repo._persist
    def fail(c,job):
        original(c,job)
        raise RuntimeError('simulated crash before commit')
    monkeypatch.setattr(repo,'_persist',fail)
    drain(repo)
    with psycopg.connect(db[0]) as c:
        assert c.execute('SELECT count(*) FROM analytics.transactions WHERE source_upload_id=%s',(row['upload_id'],)).fetchone()[0]==0
    assert repo.summary(row['upload_id'],uid,uuid4())['status']=='failed'
    monkeypatch.setattr(repo,'_persist',original)
    repo.retry(row['upload_id'],uid,uuid4()); drain(repo)
    assert repo.summary(row['upload_id'],uid,uuid4())['rows_accepted']==1

def test_summary_scoped_to_uploader(db,ingest):
    repo,_,_,_=ingest; row,_=enqueue(ingest)
    assert repo.summary(row['upload_id'],uuid4(),uuid4()) is None

def test_unknown_database_mapping_becomes_rejection(db,ingest):
    repo,uid,profile,data=ingest
    modified=profile.model_copy(update={'providers':{'DEMO':uuid4()}})
    row,_=enqueue((repo,uid,modified,data)); drain(repo)
    result=repo.summary(row['upload_id'],uid,uuid4())
    assert result['rows_accepted']==0 and result['rows_rejected']==2
    assert result['rejections'][0]['code']=='provider_unavailable'

def test_changed_mapping_same_bytes_conflicts(db,ingest):
    enqueue(ingest)
    repo,uid,profile,data=ingest
    modified=profile.model_copy(update={'allow_negative_amounts':True})
    with pytest.raises(UploadConflict): enqueue((repo,uid,modified,data))
