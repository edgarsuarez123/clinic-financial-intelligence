from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.ingestion.config import IngestionConfig
from app.ingestion.repository import UploadConflict
from test_api import MemoryStore, login
from test_ingestion import profile, HEADER, GOOD

class MemoryRepository:
    def __init__(self): self.uploads={}
    def enqueue(self,uid,digest,kind,name,profile,prepared,request_id):
        duplicate=digest in self.uploads
        if not duplicate:
            self.uploads[digest]={'upload_id':str(uuid4()),'status':'pending','total_rows':prepared.total_rows,
                'rows_accepted':0,'rows_rejected':len(prepared.rejections),'rejections':prepared.rejections,
                'failure_code':None,'currency':'USD','profile_name':name,'created_at':datetime.now(timezone.utc)}
        return self.uploads[digest],duplicate
    def summary(self,upload_id,uid,request_id):
        return next((x for x in self.uploads.values() if x['upload_id']==str(upload_id)),None)
    def retry(self,upload_id,uid,request_id): raise UploadConflict()

@pytest.fixture
def api(profile):
    store=MemoryStore(); repo=MemoryRepository()
    config=IngestionConfig(mode='synthetic',no_phi_confirmed=True,authorized_user_ids=[store.user['user_id']],profiles={'demo':profile})
    with TestClient(create_app(Settings('postgresql://unused'),store,config,repo)) as client:
        yield client,store,repo

def test_upload_is_authenticated(api):
    client,_,repo=api
    assert client.post('/api/v1/uploads/csv?profile=demo',content=(HEADER+GOOD).encode()).status_code==401
    assert not repo.uploads

def test_upload_returns_queued_summary(api):
    client,_,repo=api; _,headers=login(client)
    r=client.post('/api/v1/uploads/csv?profile=demo',content=(HEADER+GOOD).encode(),headers=headers)
    assert r.status_code==202 and r.json()['status']=='pending'
    assert r.json()['total_rows']==1
    again=client.post('/api/v1/uploads/csv?profile=demo',content=(HEADER+GOOD).encode(),headers=headers)
    assert again.status_code==200 and again.json()['duplicate']
    assert again.json()['upload_id']==r.json()['upload_id']
    assert len(repo.uploads)==1
    status=client.get('/api/v1/uploads/'+r.json()['upload_id'],headers=headers)
    assert status.status_code==200

def test_failed_preflight_never_enqueued(api):
    client,_,repo=api; _,headers=login(client)
    r=client.post('/api/v1/uploads/csv?profile=demo',content=b'patient_name,amount\nSecret,10\n',headers=headers)
    assert r.status_code==422 and r.json()['error']['code']=='header_mismatch'
    assert 'Secret' not in r.text and not repo.uploads

def test_disabled_config_blocks_upload(profile):
    store=MemoryStore(); repo=MemoryRepository()
    with TestClient(create_app(Settings('postgresql://unused'),store,IngestionConfig(),repo)) as client:
        _,headers=login(client)
        r=client.post('/api/v1/uploads/csv?profile=demo',content=b'secret',headers=headers)
        assert r.status_code==403 and not repo.uploads

def test_summary_invalid_and_missing_ids(api):
    client,_,_=api; _,headers=login(client)
    assert client.get('/api/v1/uploads/not-a-uuid',headers=headers).status_code==422
    assert client.get('/api/v1/uploads/'+str(uuid4()),headers=headers).status_code==404

def test_oversize_rejected(api):
    client,_,repo=api; _,headers=login(client)
    r=client.post('/api/v1/uploads/csv?profile=demo',content=b'a'*(10*1024*1024+1),headers=headers)
    assert r.status_code==413 and not repo.uploads
