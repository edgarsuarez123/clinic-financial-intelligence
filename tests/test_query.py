from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.query.config import QueryConfig
from app.query.schemas import Question
from app.query.catalog import CATALOG,Unreliable,validate_sql,render_explanation,validate_result
from app.query.provider import Completion,ProviderUnavailable,HTTPSChatProvider
from app.query.service import QueryService,strict_json
from app.analytics.config import AnalyticsConfig
from test_api import MemoryStore,login

START=date(2026,1,1);END=date(2026,1,31)
def body():
    return Question(question='What were revenue and net for the selected period?',start=START,end=END,acknowledge_external_processing=True)
def config(**kw):
    return QueryConfig(enabled=True,synthetic_data=True,provider_name='Synthetic test provider',endpoint='https://example.invalid/v1/chat/completions',
        model='test-model',disclosure_reference='SYNTHETIC disclosure',dpa_reference='SYNTHETIC agreement',
        input_price_per_million='1',output_price_per_million='2',pricing_currency='USD',**kw)
class Repo:
    def __init__(self): self.logs=[];self.usage_calls=[];self.cached={};self.fail=False;self.allowed=True
    def begin(self,*args):
        if self.fail: raise RuntimeError('synthetic audit outage')
        self.logs.append({'question':args[2],'outcome':'running' if self.allowed else 'rate_limited'})
        return len(self.logs),self.allowed
    def record_sql(self,key,actor,rid,sql,params): self.logs[key-1].update(sql=sql,params=params)
    def cache(self,key,actor,rid): return deepcopy(self.cached.get(key))
    def usage(self,key,actor,rid,task,completion=None): self.usage_calls.append((task,completion))
    def finish(self,key,actor,rid,outcome,sql=None,params=None,response=None,cache_key=None,cache_seconds=300,cache_hit=False):
        if self.fail: raise RuntimeError('synthetic audit outage')
        self.logs[key-1].update(outcome=outcome,sql=sql,params=params)
        if cache_key: self.cached[cache_key]=deepcopy(response)
    def costs(self,*args): return [{'pricing_currency':'USD','requests':len(self.logs),'estimated_known_cost':'0.01','unknown_usage_calls':0}]
class Executor:
    def __init__(self): self.version=1;self.calls=0
    def revision(self): return self.version
    def execute(self,query,params,revision):
        self.calls+=1
        return [{'currency':'USD','revenue':Decimal('100.10'),'expense':Decimal('25.10'),'net':Decimal('75.00'),'margin_pct':Decimal('74.92507492507492507493')}]
class Model:
    def __init__(self): self.calls=[];self.bad_sql=None;self.confidence='0.99';self.bad_fact=False;self.outage=False
    def complete(self,task,payload):
        self.calls.append((task,deepcopy(payload)))
        if self.outage: raise ProviderUnavailable()
        if task=='translate':
            value={'answerable':True,'confidence':self.confidence,'query_key':'summary','sql':self.bad_sql or CATALOG['summary'].sql,'parameters':{'start':START.isoformat(),'end':END.isoformat()}}
        else: value={'facts':[{'row':0,'column':'invented_profit' if self.bad_fact else 'net'}]}
        return Completion(json.dumps(value),100,20,'test-model')

def test_round_trip_exact_cells_usage_cache_and_invalidation():
    repo=Repo();executor=Executor();model=Model();service=QueryService(config(),repo,executor,model);actor=uuid4()
    code,result=service.ask(body(),actor,uuid4(),False)
    assert code==200 and result['answer']=='Recorded net is 75.00 USD.'
    assert result['rows'][0]['revenue']=='100.10'
    assert model.calls[1][1]['rows']==result['rows']
    assert len(repo.usage_calls)==2
    assert service.ask(body(),actor,uuid4(),False)[1]['cached'] is True
    assert len(model.calls)==2 and executor.calls==1
    executor.version+=1
    assert service.ask(body(),actor,uuid4(),False)[1]['cached'] is False
    assert len(model.calls)==4
    assert service.ask(body(),uuid4(),uuid4(),False)[1]['cached'] is False

@pytest.mark.parametrize('sql',[
    'DELETE FROM analytics.transactions','SELECT * FROM core.saved_budget',
    "SELECT pg_sleep(99)",'SELECT * FROM pg_authid','SELECT 1; DROP TABLE core.app_user',
    'WITH x AS (DELETE FROM analytics.transactions RETURNING *) SELECT * FROM x',
    "SELECT nextval('audit.audit_log_audit_id_seq')",'COPY analytics.transactions TO STDOUT',
    'SELECT * INTO public.stolen FROM analytics.transactions',
    CATALOG['summary'].sql+'; SELECT 1',CATALOG['summary'].sql+' FOR UPDATE',
    CATALOG['summary'].sql.replace('analytics.nl_practice_daily','analytics.nl_provider_daily'),
])
def test_sql_allowlist_rejects_out_of_scope_queries(sql):
    with pytest.raises(Unreliable): validate_sql('summary',sql,{'start':START.isoformat(),'end':END.isoformat()},START,END,False)

def test_dates_provider_access_and_unknown_catalog_rejected():
    for key,sql,params in [('summary',CATALOG['summary'].sql,{'start':"2026-01-01';DELETE",'end':END.isoformat()}),
        ('providers',CATALOG['providers'].sql,{'start':START.isoformat(),'end':END.isoformat()}),('unknown','SELECT 1',{})]:
        with pytest.raises(Unreliable): validate_sql(key,sql,params,START,END,False)

def test_low_confidence_and_invalid_sql_never_execute():
    for confidence,sql in [('0.5',None),('1','DELETE FROM core.saved_budget')]:
        repo=Repo();executor=Executor();model=Model();model.confidence=confidence;model.bad_sql=sql
        code,result=QueryService(config(),repo,executor,model).ask(body(),uuid4(),uuid4(),False)
        assert result['status']=='refused' and executor.calls==0
        assert len(repo.usage_calls)==1 and repo.logs[-1]['outcome']=='refused'

def test_bad_explanation_outage_and_rate_limit():
    repo=Repo();executor=Executor();model=Model();model.bad_fact=True
    service=QueryService(config(),repo,executor,model)
    assert service.ask(body(),uuid4(),uuid4(),False)[1]['status']=='refused'
    assert not repo.cached
    model.outage=True
    assert service.ask(body(),uuid4(),uuid4(),False)[0]==503
    assert repo.usage_calls[-1][1] is None
    count=len(model.calls);repo.allowed=False
    assert service.ask(body(),uuid4(),uuid4(),False)[0]==429
    assert len(model.calls)==count

def test_empty_results_and_result_validation():
    assert render_explanation([],CATALOG['summary'],[])=='No recorded data was returned for the selected dates.'
    with pytest.raises(Unreliable): validate_result(CATALOG['summary'],[{'revenue':'1'}])
    row={'currency':None,'revenue':'1','expense':'0','net':'1','margin_pct':'100'}
    with pytest.raises(Unreliable): validate_result(CATALOG['summary'],[row])
    with pytest.raises(Unreliable): validate_result(CATALOG['summary'],[row]*101)
    for raw in ['{"a":1,"a":2}','{"a":NaN}','[]']:
        with pytest.raises(ValueError): strict_json(raw)

def test_config_default_disabled_and_requires_real_setup():
    assert not QueryConfig().enabled
    with pytest.raises(ValueError): QueryConfig(enabled=True)
    with pytest.raises(ValueError): QueryConfig(endpoint='http://example.invalid')
    with pytest.raises(ValueError): QueryConfig(endpoint='https://user:secret@example.invalid')


def test_api_authorization_disclosure_and_cost_privacy():
    store=MemoryStore();uid=store.user['user_id'];cfg=config(authorized_user_ids=[uid])
    repo=Repo();executor=Executor();model=Model()
    analytics=AnalyticsConfig(authorized_user_ids=[uid])
    with TestClient(create_app(Settings('postgresql://unused'),store,analytics_config=analytics,query_config=cfg,
        query_repo=repo,query_executor=executor,query_provider=model),raise_server_exceptions=False) as client:
        assert client.post('/api/v1/questions',json=body().model_dump(mode='json')).status_code==401
        _,headers=login(client)
        request=body().model_dump(mode='json');request['acknowledge_external_processing']=False
        assert client.post('/api/v1/questions',headers=headers,json=request).status_code==422
        request['acknowledge_external_processing']=True;request['allow_provider_data']=True
        assert client.post('/api/v1/questions',headers=headers,json=request).status_code==403
        assert not model.calls
        request['allow_provider_data']=False
        response=client.post('/api/v1/questions',headers=headers,json=request)
        assert response.status_code==200 and response.json()['rows'][0]['net']=='75.00'
        url='/api/v1/questions/costs?start=2026-01-01&end=2026-01-31'
        assert client.get(url,headers=headers).status_code==403
        cfg.cost_report_user_ids.append(uid)
        assert client.get(url,headers=headers).json()['rows'][0]['estimated_known_cost']=='0.01'
        repo.fail=True
        assert client.post('/api/v1/questions',headers=headers,json=request).status_code==500
        assert client.get('/api/v1/health',headers=headers).status_code==200

def test_https_provider_contract_and_outages(monkeypatch):
    captured={}
    class Response:
        status_code=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def iter_content(self,size):
            yield json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"facts":[]}'}}],
                'usage':{'prompt_tokens':123,'completion_tokens':7},'model':'test-model'}).encode()
    response=Response()
    def post(endpoint,**kwargs): captured.update(kwargs);return response
    monkeypatch.setattr('requests.post',post)
    adapter=HTTPSChatProvider(config(),'synthetic-secret')
    result=adapter.complete('explain',{'rows':[]})
    assert (result.input_tokens,result.output_tokens)==(123,7)
    assert captured['allow_redirects'] is False and captured['json']['store'] is False
    assert 'synthetic-secret' not in json.dumps(captured['json'])
    response.status_code=302
    with pytest.raises(ProviderUnavailable): adapter.complete('translate',{})
    response.status_code=500
    with pytest.raises(ProviderUnavailable): adapter.complete('translate',{})
    with pytest.raises(ValueError): QueryConfig(input_price_per_million=1.01)


def test_provider_permission_changes_invalidate_cache_scope():
    repo=Repo();executor=Executor();model=Model();actor=uuid4()
    service=QueryService(config(),repo,executor,model)
    service.ask(body(),actor,uuid4(),True)
    assert service.ask(body(),actor,uuid4(),False)[1]['cached'] is False
    assert all(not q['provider_access'] for q in model.calls[2][1]['catalog'])


def test_failed_query_audit_prevents_financial_execution(monkeypatch):
    repo=Repo();executor=Executor();model=Model()
    def fail(*args): raise RuntimeError('synthetic audit outage')
    monkeypatch.setattr(repo,'record_sql',fail)
    with pytest.raises(RuntimeError): QueryService(config(),repo,executor,model).ask(body(),uuid4(),uuid4(),False)
    assert executor.calls==0
