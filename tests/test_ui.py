from pathlib import Path
from streamlit.testing.v1 import AppTest

UI=Path(__file__).resolve().parent.parent/'ui/app.py'

def test_login_surface_has_no_financial_data():
    app=AppTest.from_file(str(UI),default_timeout=10).run()
    assert not app.exception
    assert [x.label for x in app.text_input]==['Username','Password']
    assert app.button[0].label=='Sign in'
    assert not app.metric

def test_logged_in_unconfigured_account_sees_onboarding_message(monkeypatch):
    class Response:
        status_code=200
        content=b'{}'
        def json(self): return {'enabled':False,'mode':'disabled','profiles':[]}
    monkeypatch.setattr('requests.request',lambda *a,**k:Response())
    app=AppTest.from_file(str(UI),default_timeout=10)
    app.session_state['token']='synthetic-token'
    app.run()
    assert not app.exception
    assert 'not configured' in app.info[0].value
