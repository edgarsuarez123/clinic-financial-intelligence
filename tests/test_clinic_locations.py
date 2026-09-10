from datetime import date
from uuid import uuid4
import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.analytics.config import AnalyticsConfig
from app.analytics.repository import AnalyticsRepository
from app.ingestion.config import IngestionConfig
from app.ingestion.repository import UploadConflict
from app.ingestion.validation import prepare
from test_api import MemoryStore,login
from test_ingestion import profile,HEADER,GOOD
from test_ingestion_api import MemoryRepository
from test_ingestion_postgres import ingest,db,drain
from test_analytics_api import Repository

def test_location_required_and_approved_before_upload(profile):
    store=MemoryStore()
    class Repo(MemoryRepository):
        def enqueue(self,*args,clinic_location=None):
            self.location=clinic_location
            return super().enqueue(*args)
    repo=Repo()
    config=IngestionConfig(mode='synthetic',no_phi_confirmed=True,
        authorized_user_ids=[store.user['user_id']],profiles={'demo':profile},clinic_locations=['North','South'])
    with TestClient(create_app(Settings('postgresql://unused'),store,config,repo)) as client:
        _,headers=login(client)
        for query in ('','&clinic_location=Unknown'):
            response=client.post('/api/v1/uploads/csv?profile=demo'+query,content=(HEADER+GOOD).encode(),headers=headers)
            assert response.status_code==422 and not repo.uploads
        response=client.post('/api/v1/uploads/csv?profile=demo&clinic_location=North',content=(HEADER+GOOD).encode(),headers=headers)
        assert response.status_code==202 and repo.location=='North'

def test_dashboard_location_is_forwarded_and_permissions_preserved():
    store=MemoryStore()
    class Repo(Repository):
        def rows(self,*args,clinic_location=None,**kwargs):
            self.location=clinic_location
            return super().rows(*args,**kwargs)
    repo=Repo()
    with TestClient(create_app(Settings('postgresql://unused'),store,
        analytics_config=AnalyticsConfig(authorized_user_ids=[store.user['user_id']]),analytics_repo=repo)) as client:
        url='/api/v1/analytics/dashboard?start=2026-01-01&end=2026-01-31&clinic_location=North'
        assert client.get(url).status_code==401
        _,headers=login(client)
        assert client.get(url,headers=headers).status_code==200
        assert repo.location=='North'

@pytest.mark.integration
def test_location_persists_and_duplicate_cannot_be_reassigned(db,ingest):
    repo,uid,profile,data=ingest
    digest=hashlib.sha256(data).hexdigest()
    args=(uid,digest,'csv','demo',profile,prepare(data,'csv',profile),uuid4())
    row,duplicate=repo.enqueue(*args,clinic_location='North')
    assert not duplicate and row['clinic_location']=='North'
    assert repo.enqueue(*args,clinic_location='North')[1]
    with pytest.raises(UploadConflict): repo.enqueue(*args,clinic_location='South')
    drain(repo)
    analytics=AnalyticsRepository(Settings(db[1]))
    north,_=analytics.rows(uid,uuid4(),date(2026,1,1),date(2026,1,31),clinic_location='North')
    south,_=analytics.rows(uid,uuid4(),date(2026,1,1),date(2026,1,31),clinic_location='South')
    assert len(north)==1 and not south
    assert 'North' in analytics.metadata(uid,uuid4())['clinic_locations']
