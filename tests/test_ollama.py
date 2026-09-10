import json
from uuid import uuid4
import pytest
from app.query.config import QueryConfig
from app.query.provider import OllamaProvider,ProviderUnavailable
from app.query.service import QueryService
from app.main import create_app
from app.settings import Settings
from test_api import MemoryStore
from test_query import Repo,Executor,body

def config(**updates):
    return QueryConfig.model_validate(dict(enabled=True,transport='ollama',synthetic_data=True,
        provider_name='Local Ollama',endpoint='http://ollama:11434/api/chat',model='qwen2.5:7b',
        input_price_per_million='0',output_price_per_million='0',pricing_currency='USD')|updates)

@pytest.mark.parametrize('updates',[
    {'synthetic_data':False},{'endpoint':'http://example.com:11434/api/chat'},
    {'endpoint':'http://ollama:11434/api/chat?redirect=remote'},
    {'endpoint':'http://user:password@ollama:11434/api/chat'},
    {'endpoint':'http://ollama:80/api/chat'}, {'endpoint':'http://ollama:11434/api/generate'},
    {'input_price_per_million':'1'},{'model':'example:cloud'},
])
def test_unsafe_local_config_rejected(updates):
    with pytest.raises(ValueError):config(**updates)

@pytest.mark.parametrize('environment',['production','staging'])
def test_local_provider_blocked_outside_dev_test(environment):
    with pytest.raises(ValueError):create_app(Settings('postgresql://unused',app_environment=environment),MemoryStore(),query_config=config())

def response(monkeypatch,value,status=200):
    class Response:
        status_code=status
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield json.dumps(value).encode()
    def post(self,url,**kw):
        assert self.trust_env is False
        assert url=='http://ollama:11434/api/chat'
        assert kw['allow_redirects'] is False and kw['stream'] is True
        assert kw['json']['stream'] is False
        assert kw['json']['format']=='json' or kw['json']['format']['additionalProperties'] is False
        assert kw['json']['options']['temperature']==0
        return Response()
    monkeypatch.setattr('requests.Session.post',post)

def test_native_completion_and_usage(monkeypatch):
    response(monkeypatch,{'done':True,'done_reason':'stop','message':{'content':'{"answerable":false}'},'model':'qwen2.5:7b','prompt_eval_count':50,'eval_count':10})
    result=OllamaProvider(config()).complete('translate',{})
    assert result.input_tokens==50 and result.output_tokens==10
    assert json.loads(result.content)=={'answerable':False}

@pytest.mark.parametrize('value,status',[
    ({},302), ({},500), ({'done':False},200),
    ({'done':True,'done_reason':'length','message':{'content':'{}'}},200),
    ({'done':True,'done_reason':'stop','message':{'content':12}},200),
    ({'done':True,'done_reason':'stop','message':{'content':'x'*270000}},200)
])
def test_unavailable_and_truncated_fail_closed(monkeypatch,value,status):
    response(monkeypatch,value,status)
    with pytest.raises(ProviderUnavailable):OllamaProvider(config()).complete('translate',{})

def test_local_output_still_passes_sql_boundary(monkeypatch):
    response(monkeypatch,{'done':True,'done_reason':'stop','message':{'content':json.dumps({'answerable':True,'confidence':1,'query_key':'summary','sql':'DELETE FROM core.app_user','parameters':{'start':'2026-01-01','end':'2026-01-31'}})}})
    executor=Executor()
    status,result=QueryService(config(),Repo(),executor,OllamaProvider(config())).ask(body(),uuid4(),uuid4(),False)
    assert status==200 and result['status']=='refused' and executor.calls==0

def test_local_catalog_selection_supplies_trusted_sql(monkeypatch):
    from dataclasses import asdict
    from app.query.catalog import CATALOG
    response(monkeypatch,{'done':True,'done_reason':'stop','message':{'content':json.dumps({
        'answerable':True,'confidence':0.99,'query_key':'monthly'})}})
    result=OllamaProvider(config()).complete('translate',{'question':'Show monthly trends',
        'catalog':[asdict(CATALOG['monthly'])],'selected_dates':{'start':'2026-01-01','end':'2026-03-31'}})
    decoded=json.loads(result.content)
    assert decoded['sql']==CATALOG['monthly'].sql
    assert decoded['parameters']=={'start':'2026-01-01','end':'2026-03-31'}
