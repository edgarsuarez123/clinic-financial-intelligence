from pathlib import Path
from streamlit.testing.v1 import AppTest
from fastapi.testclient import TestClient
from test_api import MemoryStore,login
from app.main import create_app
from app.settings import Settings
from app.simulation.config import SimulationConfig
from test_budgets import MemoryBudgets

def test_synthetic_budget_submit_and_assumptions(monkeypatch):
    store=MemoryStore(); budgets=MemoryBudgets(store)
    with TestClient(create_app(Settings('postgresql://unused'),store,budget_repo=budgets,simulation_config=SimulationConfig(authorized_user_ids=[store.user['user_id']],synthetic_data=True))) as client:
        token,_=login(client)
        class Response:
            content=b'{}'
            def __init__(self,response): self.status_code=response.status_code; self.value=response.json()
            def json(self): return self.value
        def request(method,url,**kwargs):
            kwargs.pop('timeout',None)
            return Response(client.request(method,'/api/v1/'+url.split('/api/v1/')[1],**kwargs))
        monkeypatch.setattr('requests.request',request)
        app=AppTest.from_file(str(Path('ui/app.py').resolve()),default_timeout=20)
        app.session_state['token']=token; app.run()
        app.sidebar.radio[0].set_value('Staffing & clinic budget').run()
        assert not app.exception
        next(b for b in app.button if b.label=='Load explicitly synthetic example').click().run()
        next(b for b in app.button if b.label=='Save & calculate').click().run()
        assert not app.exception
        assert not app.error
        assert len(app.metric)==6
        assert len(app.get('vega_lite_chart'))==9
        assert len([s for s in app.subheader if s.value=='Full assumptions used'])==3

        assert len(budgets.rows)==1
        # Fresh UI/session reopens inputs and results without retyping or recalculating.
        again=AppTest.from_file(str(Path('ui/app.py').resolve()),default_timeout=20)
        again.session_state['token']=token; again.run()
        again.sidebar.radio[0].set_value('Staffing & clinic budget').run()
        again.selectbox[0].select(next(iter(budgets.rows))).run()
        next(b for b in again.button if b.label=='Open saved budget').click().run()
        assert not again.exception and len(again.metric)==6
        assert next(t for t in again.text_input if t.label=='Budget name').value=='Synthetic clinic example'
        next(t for t in again.text_input if t.label=='Budget name').set_value('Higher costs')
        next(t for t in again.text_input if t.label=='Existing monthly clinic revenue').set_value('25000')
        next(b for b in again.button if b.label=='Save as new budget').click().run()
        assert not again.exception and len(budgets.rows)==2
        again.multiselect[0].set_value(list(budgets.rows)).run()
        next(b for b in again.button if b.label=='Compare saved budgets').click().run()
        assert not again.exception and len(again.get('vega_lite_chart'))==12
        assert any(s.value=='Compare saved cost plans' for s in again.subheader)
