from datetime import date
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from app.analytics.calculations import analytics
from app.analytics.routes import json_exact
from test_analytics import six_weeks,START,END
from ui.dashboard import chart_cents,trend_rows

UI=Path(__file__).resolve().parent.parent/'ui/app.py'

def test_full_dashboard_renders_exact_metrics_and_charts(monkeypatch,six_weeks):
    result=json_exact(analytics(six_weeks,START,END))
    result.update(currency='USD',category_labels={'fixed_cost':'Fixed costs','variable_cost':'Variable costs'})
    class Response:
        status_code=200; content=b'{}'
        def __init__(self,value): self.value=value
        def json(self): return self.value
    def request(method,url,**kwargs):
        if url.endswith('/config'): return Response({'enabled':True,'provider_access':False,'synthetic_data':True})
        if url.endswith('/metadata'): return Response({'row_count':12,'first_date':START.isoformat(),'last_date':END.isoformat()})
        return Response(result)
    monkeypatch.setattr('requests.request',request)
    app=AppTest.from_file(str(UI),default_timeout=15)
    app.session_state['token']='synthetic'; app.run()
    assert not app.exception
    values={x.label:x.value for x in app.metric}
    assert values['Revenue']=='USD 2,100.00' and values['Net']=='USD 1,520.00'
    assert len(app.get('vega_lite_chart'))==3
    assert 'Synthetic' in app.warning[0].value

def test_empty_dashboard_render(monkeypatch):
    class Response:
        status_code=200; content=b'{}'
        def __init__(self,value): self.value=value
        def json(self): return self.value
    def request(method,url,**kwargs):
        return Response({'enabled':True,'provider_access':False} if url.endswith('/config') else
                        {'row_count':0,'first_date':None,'last_date':None})
    monkeypatch.setattr('requests.request',request)
    app=AppTest.from_file(str(UI),default_timeout=10)
    app.session_state['token']='synthetic'; app.run()
    assert not app.exception and 'No completed financial imports' in app.info[0].value

def test_chart_uses_exact_integer_cents_and_breaks_missing_periods():
    assert chart_cents('0.10')==10
    assert chart_cents('1.005')==101
    rows=trend_rows([{'period_start':'2026-01-05','revenue':'10'},
                     {'period_start':'2026-01-12','revenue':None},
                     {'period_start':'2026-01-19','revenue':'20'}],[('revenue','Revenue')])
    assert rows[0]['segment']!=rows[1]['segment']
    with pytest.raises(ValueError): chart_cents('9999999999999999.00')
