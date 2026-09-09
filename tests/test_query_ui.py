from pathlib import Path
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from app.main import create_app
from app.settings import Settings
from app.analytics.config import AnalyticsConfig
from test_api import MemoryStore,login
from test_query import config,Repo,Executor,Model,START,END

def test_question_ui_disclosure_answer_sql_and_raw_table(monkeypatch):
    store=MemoryStore();uid=store.user['user_id'];model=Model()
    with TestClient(create_app(Settings('postgresql://unused'),store,analytics_config=AnalyticsConfig(authorized_user_ids=[uid]),
        query_config=config(authorized_user_ids=[uid]),query_repo=Repo(),query_executor=Executor(),query_provider=model)) as client:
        token,_=login(client)
        class Response:
            content=b'{}'
            def __init__(self,response): self.status_code=response.status_code;self.value=response.json()
            def json(self): return self.value
        def request(method,url,**kwargs):
            kwargs.pop('timeout',None)
            return Response(client.request(method,'/api/v1/'+url.split('/api/v1/')[1],**kwargs))
        monkeypatch.setattr('requests.request',request)
        app=AppTest.from_file(str(Path('ui/app.py').resolve()),default_timeout=20)
        app.session_state['token']=token;app.run()
        app.sidebar.radio[0].set_value('Financial questions').run()
        assert not app.exception and any('third-party' in x.value for x in app.info)
        app.text_area[0].set_value('What was net for the selected period?')
        app.date_input[0].set_value(START);app.date_input[1].set_value(END)
        next(x for x in app.checkbox if 'acknowledge' in x.label).check()
        next(b for b in app.button if b.label=='Ask financial question').click().run()
        assert not app.exception and not app.error
        assert any('75.00 USD' in x.value for x in app.markdown)
        assert len(app.code)==1 and len(app.dataframe)==1
        assert len(model.calls)==2
        next(b for b in app.button if b.label=='Ask financial question').click().run()
        assert len(model.calls)==2 and not app.exception
