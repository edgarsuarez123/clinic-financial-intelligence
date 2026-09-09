import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
from scripts.prepare_environment import prepare
from app.main import create_app
from app.settings import Settings
from app.ingestion.config import IngestionConfig
from app.analytics.config import AnalyticsConfig
from app.simulation.config import SimulationConfig
from app.query.config import QueryConfig
from app.query.provider import DemoProvider
from app.query.service import QueryService
from app.ingestion.validation import prepare as prepare_upload
from test_api import MemoryStore
from test_query import Repo,Executor,body


def demo_config():
    return QueryConfig(enabled=True,transport='demo',synthetic_data=True,provider_name='Synthetic local provider',model='demo-catalog-v1',
        input_price_per_million='0',output_price_per_million='0',pricing_currency='USD')

def test_environment_isolation_defaults_and_no_overwrite(tmp_path):
    dev=prepare('dev',tmp_path);test=prepare('test',tmp_path);production=prepare('production',tmp_path)
    def read_env(path): return dict(line.split('=',1) for line in (path/'.env').read_text().splitlines())
    d=read_env(dev);t=read_env(test);p=read_env(production)
    assert len({d['APP_DB_PASSWORD'],t['APP_DB_PASSWORD'],p['APP_DB_PASSWORD']})==3
    assert d['CONFIG_DIRECTORY']!=t['CONFIG_DIRECTORY'] and d['API_PORT']!=t['API_PORT']
    assert t['CONFIRM_DISPOSABLE_TEST_DATABASE']=='true' and p['CONFIRM_DISPOSABLE_TEST_DATABASE']=='false'
    assert os.stat(dev/'.env').st_mode & 0o777==0o600
    for root in (dev,test,production):
        cfg=root/'config'
        assert IngestionConfig.model_validate_json((cfg/'ingestion.json').read_text()).mode=='disabled'
        assert not AnalyticsConfig.model_validate_json((cfg/'analytics.json').read_text()).authorized_user_ids
        assert not SimulationConfig.model_validate_json((cfg/'simulation.json').read_text()).authorized_user_ids
        assert not QueryConfig.model_validate_json((cfg/'query.json').read_text()).enabled
    with pytest.raises(ValueError): prepare('dev',tmp_path)
    with pytest.raises(ValueError): prepare('../escape',tmp_path)

def test_demo_provider_restricted_to_dev_test_and_has_no_network(monkeypatch):
    def network(*args,**kwargs): pytest.fail('Local demo must not contact an external API')
    monkeypatch.setattr('requests.post',network)
    for environment in ('production','staging'):
        with pytest.raises(ValueError): create_app(Settings('postgresql://unused',app_environment=environment),MemoryStore(),query_config=demo_config())
    for environment in ('dev','test'):
        assert create_app(Settings('postgresql://unused',app_environment=environment),MemoryStore(),query_config=demo_config())
    request=body().model_copy(update={'question':'show the financial summary'})
    code,result=QueryService(demo_config(),Repo(),Executor(),DemoProvider()).ask(request,uuid4(),uuid4(),False)
    assert code==200 and result['status']=='answered'
    request=request.model_copy(update={'question':'Invent revenue for next year'})
    assert QueryService(demo_config(),Repo(),Executor(),DemoProvider()).ask(request,uuid4(),uuid4(),False)[1]['status']=='refused'


def test_extended_dummy_history_uses_strict_parser():
    from app.ingestion.config import Profile
    profile=Profile(columns={k:k for k in ('date','amount','type','category','provider')},date_format='%Y-%m-%d',
        types={'revenue':'revenue','expense':'expense'},categories={'Collections':uuid4(),'Supplies':uuid4()},
        providers={'DEMO1':uuid4()},allow_negative_amounts=False,currency='USD')
    result=prepare_upload(Path('examples/synthetic-history.csv').read_bytes(),'csv',profile)
    assert result.total_rows==52 and len(result.rows)==52 and result.rejections==[]
