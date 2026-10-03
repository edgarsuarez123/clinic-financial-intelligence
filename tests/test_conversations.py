from copy import deepcopy
from datetime import datetime,timezone,date
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.analytics.config import AnalyticsConfig
from app.simulation.config import SimulationConfig
from app.simulation.repository import BudgetMissing,BudgetConflict
from app.query.chat_schemas import ConversationCreate,Context,Turn
from app.query.chat_service import ChatService,validated_narrative
from app.query.chat_catalog import CHAT_CATALOG
from app.query.provider import Completion,ProviderUnavailable
from app.query.service import QueryService
from app.query.chat_routes import public_document
from test_api import MemoryStore,login
from test_query import Repo,config
from test_budgets import MemoryBudgets,create_body
from test_simulation import payload

class MemoryConversations:
    """API contract double only. SQL locking/durability is covered separately."""
    def __init__(self): self.rows={};self.attempts={}
    def create(self,body,actor,rid):
        key=str(body.conversation_id)
        if key not in self.rows:self.rows[key]={'conversation_id':key,'owner_id':str(actor),'title':body.title,'revision':1,'turns':[], 'deleted_at':None,'requires_provider_access':False,'requires_simulation_access':False}
        row=self.get(key,actor,rid,True,True)
        if row['title']!=body.title or row['revision']!=1:raise BudgetConflict()
        return row
    def get(self,key,actor,rid,p,s):
        row=self.rows.get(str(key))
        if not row or row['owner_id']!=str(actor) or row['deleted_at'] or row['requires_provider_access'] and not p or row['requires_simulation_access'] and not s:raise BudgetMissing()
        return deepcopy(row)
    def list(self,actor,rid,p,s,offset=0):
        rows=[]
        for k in self.rows:
            try:rows.append(self.get(k,actor,rid,p,s))
            except BudgetMissing:pass
        return {'conversations':rows[offset:offset+50],'has_more':len(rows)>offset+50}
    def change(self,key,actor,rid,p,s,revision,title=None,delete=False):
        self.get(key,actor,rid,p,s);row=self.rows[str(key)]
        if row['revision']!=revision:raise BudgetConflict()
        row.update(title=title or row['title'],deleted_at=datetime.now(timezone.utc) if delete else None,revision=revision+1)
        return deepcopy(row)
    def protect(self,key,actor,rid,p,s):
        self.get(key,actor,rid,True,True);row=self.rows[str(key)]
        row['requires_provider_access']|=p;row['requires_simulation_access']|=s
    def begin(self,key,body,actor,rid,p,s):
        self.get(key,actor,rid,p,s);row=self.rows[str(key)];context=body.context.model_dump(mode='json')
        existing=next((t for t in row['turns'] if t['turn_id']==str(body.turn_id)),None)
        if existing:
            if existing['question']!=body.question or existing['context']!=context or existing['status']=='running':raise BudgetConflict()
            return deepcopy(existing),None
        if body.expected_revision!=row['revision'] or any(t['status']=='running' for t in row['turns']):raise BudgetConflict()
        row['turns'].append({'turn_id':str(body.turn_id),'position':len(row['turns'])+1,'question':body.question,'context':context,'status':'running','response':None});row['revision']+=1
        attempt=uuid4();self.attempts[str(body.turn_id)]=attempt;return None,attempt
    def finish(self,key,turn,attempt,actor,rid,result,p,s):
        self.get(key,actor,rid,True,True)
        if self.attempts[str(turn)]!=attempt:raise BudgetConflict()
        row=self.rows[str(key)];t=next(t for t in row['turns'] if t['turn_id']==str(turn));t.update(response=deepcopy(result),status=result['status']);self.protect(key,actor,rid,p,s)

class ChatModel:
    def __init__(self,selection=None):self.calls=[];self.selection=selection or {'tool':'analytics','query_key':'monthly','confidence':'1'};self.outage=False
    def complete(self,task,payload):
        self.calls.append((task,deepcopy(payload)))
        if self.outage:raise ProviderUnavailable()
        if task=='chat_plan':value=self.selection
        else:value={'interpretation':[{'text':'Recorded net is {{f0_0_net}}; this alone does not establish the cause.','evidence':['f0_0_net']}],'recommendations':[]}
        return Completion(json.dumps(value),10,10,'test')

class ChatExecutor:
    def __init__(self):self.calls=[]
    def revision(self):return 1
    def execute_chat(self,query,params,revision):
        self.calls.append((query,params,revision))
        return [{'period':'2026-01-01','currency':'USD','revenue':'100.10','expense':'25.10','net':'75.00','margin_pct':'74.925074925074925'}]

def setup(selection=None,environment='test'):
    store=MemoryStore();uid=store.user['user_id'];conversations=MemoryConversations();budgets=MemoryBudgets(store);repo=Repo();model=ChatModel(selection);executor=ChatExecutor()
    analytics=AnalyticsConfig(authorized_user_ids=[uid]);simulation=SimulationConfig(authorized_user_ids=[uid]);cfg=config(authorized_user_ids=[uid])
    app=create_app(Settings('postgresql://unused',app_environment=environment),store,analytics_config=analytics,simulation_config=simulation,
        budget_repo=budgets,query_config=cfg,query_repo=repo,query_executor=executor,query_provider=model,conversation_repo=conversations)
    return app,store,conversations,budgets,repo,model,executor,analytics,simulation

def turn(**kwargs):return {'turn_id':str(uuid4()),'question':'Show monthly trends','expected_revision':1,'context':{'start':'2026-01-01','end':'2026-01-31','budget_ids':[]},**kwargs}

def test_conversation_persists_reopens_followups_retries_and_production_hides_sql():
    app,store,chats,budgets,repo,model,executor,*_=setup(environment='production');key=str(uuid4());body=turn()
    with TestClient(app) as c:
        _,h=login(c);url='/api/v1/questions/conversations'
        assert c.post(url,json={'conversation_id':key}).status_code==401
        assert c.post(url,headers=h,json={'conversation_id':key,'title':'Monthly review'}).status_code==200
        r=c.post(url+'/'+key+'/turns',headers=h,json=body)
        assert r.status_code==200,r.text
        assert r.json()['revision']==2 and len(r.json()['turns'])==1
        assert 'sql' not in r.text and 'owner_id' not in r.text
        assert '75.00 USD' in r.json()['turns'][0]['response']['interpretation'][0]['text']
        calls=len(model.calls)
        assert c.post(url+'/'+key+'/turns',headers=h,json=body).json()==r.json()
        assert len(model.calls)==calls
        follow=turn(question='Show that as a table',expected_revision=2)
        assert c.post(url+'/'+key+'/turns',headers=h,json=follow).status_code==200
        assert model.calls[-2][1]['history'][0]['question']=='Show monthly trends'
        assert c.patch(url+'/'+key,headers=h,json={'title':'Renamed','expected_revision':1}).status_code==409
        assert c.patch(url+'/'+key,headers=h,json={'title':'Renamed','expected_revision':3}).status_code==200
    with TestClient(app) as c:
        _,h=login(c);r=c.get(url+'/'+key,headers=h).json()
        assert len(r['turns'])==2 and r['title']=='Renamed'
        assert c.request('DELETE',url+'/'+key,headers=h,json={'expected_revision':4}).status_code==200
        assert c.get(url+'/'+key,headers=h).status_code==404

def test_saved_scenario_read_what_if_is_draft_and_revocation_hides_context():
    app,store,chats,budgets,repo,model,executor,analytics,simulation=setup()
    key=str(uuid4());saved=create_body()
    with TestClient(app) as c:
        _,h=login(c);c.post('/api/v1/simulations/budgets',headers=h,json=saved)
        model.selection={'tool':'what_if','confidence':'1','budget_ids':[saved['budget_id']],
            'changes':[{'kind':'cost_percent','row_index':0,'from_month':2,'through_month':2,'percent':'10'}]}
        c.post('/api/v1/questions/conversations',headers=h,json={'conversation_id':key})
        b=turn(question='Increase the first expense by 10% in month 2',context={'start':'2026-01-01','end':'2026-01-31','budget_ids':[saved['budget_id']]})
        r=c.post(f'/api/v1/questions/conversations/{key}/turns',headers=h,json=b)
        assert r.status_code==200,r.text
        response=r.json()['turns'][0]['response'];assert response['status']=='answered',response
        assert response['draft']['plan']['clinic_costs'][0]['monthly_amounts']=={'2':'2200.00'}
        assert response['sources'][0]['revision']==1
        assert budgets.rows[saved['budget_id']]['revision']==1
        assert not executor.calls
        simulation.authorized_user_ids.clear()
        assert c.get(f'/api/v1/questions/conversations/{key}',headers=h).status_code==404

def test_model_cannot_use_foreign_budget_or_unreviewed_query():
    app,store,chats,budgets,repo,model,executor,*_=setup({'tool':'analytics','query_key':'DROP TABLE','confidence':'1'})
    with TestClient(app) as c:
        _,h=login(c);key=str(uuid4());url='/api/v1/questions/conversations/'+key
        c.post('/api/v1/questions/conversations',headers=h,json={'conversation_id':key})
        r=c.post(url+'/turns',headers=h,json=turn()).json()
        assert r['turns'][0]['response']['status']=='refused' and r['turns'][0]['response']['error_code']=='invalid_request' and not executor.calls
        model.selection={'tool':'scenarios','budget_ids':[str(uuid4())],'confidence':'1'}
        r=c.post(url+'/turns',headers=h,json=turn(expected_revision=2)).json()
        assert r['turns'][1]['response']['status']=='refused' and r['turns'][1]['response']['error_code']=='missing_setup'
        chats.rows[key]['owner_id']=str(uuid4())
        assert c.get(url,headers=h).status_code==404

def test_narrative_requires_existing_evidence_and_no_invented_amounts():
    facts=[{'id':'f','value':'75.00','unit':'USD'}]
    good={'interpretation':[{'text':'Net is {{f}}.','evidence':['f']}]}
    assert validated_narrative(json.dumps(good),facts,False)['interpretation'][0]['text']=='Net is 75.00 USD.'
    for text,refs in [('Net is $900.',['f']),('Net is {{missing}}.',['f']),('Costs increased.',['missing'])]:
        with pytest.raises(ValueError):validated_narrative(json.dumps({'interpretation':[{'text':text,'evidence':refs}]}),facts,False)
    assert 'sql' not in public_document({'turns':[{'response':{'sql':'hidden','answer':'ok'}}]})['turns'][0]['response']

def test_respond_tool_returns_conversational_answer_without_sql():
    app,store,chats,budgets,repo,model,executor,*_=setup({'tool':'respond','confidence':'0.9','response_text':'Hello! I can help with clinic financial questions.'})
    with TestClient(app) as c:
        _,h=login(c);key=str(uuid4());url='/api/v1/questions/conversations/'+key
        c.post('/api/v1/questions/conversations',headers=h,json={'conversation_id':key})
        r=c.post(url+'/turns',headers=h,json=turn()).json()
        response=r['turns'][0]['response']
        assert response['status']=='answered'
        assert 'Hello' in response['answer']
        assert response['tables']==[]
        assert response['facts']==[]
        assert not executor.calls

def test_clarify_tool_returns_helpful_answer_not_refusal():
    app,store,chats,budgets,repo,model,executor,*_=setup({'tool':'clarify','confidence':'0.5','clarification':'Which time period are you asking about?'})
    with TestClient(app) as c:
        _,h=login(c);key=str(uuid4());url='/api/v1/questions/conversations/'+key
        c.post('/api/v1/questions/conversations',headers=h,json={'conversation_id':key})
        r=c.post(url+'/turns',headers=h,json=turn()).json()
        response=r['turns'][0]['response']
        assert response['status']=='answered'
        assert 'time period' in response['answer']
        assert not executor.calls

def test_provider_outage_and_failed_narration_keep_persistent_valid_results():
    app,store,chats,budgets,repo,model,executor,*_=setup()
    with TestClient(app) as c:
        _,h=login(c);key=str(uuid4());url='/api/v1/questions/conversations/'+key
        c.post('/api/v1/questions/conversations',headers=h,json={'conversation_id':key})
        model.outage=True
        r=c.post(url+'/turns',headers=h,json=turn()).json()
        assert r['turns'][0]['status']=='unavailable' and r['turns'][0]['response']['error_code']=='model_unavailable' and not executor.calls
        model.outage=False;repo.allowed=False
        r=c.post(url+'/turns',headers=h,json=turn(expected_revision=2)).json()
        assert r['turns'][1]['status']=='rate_limited' and r['turns'][1]['response']['error_code']=='rate_limited'
