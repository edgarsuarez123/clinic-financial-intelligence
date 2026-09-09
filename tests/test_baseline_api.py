from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.analytics.config import AnalyticsConfig
from app.analytics.calculations import Transaction
from app.simulation.config import SimulationConfig
from test_api import MemoryStore, login


def test_baseline_requires_analytics_access_and_returns_decimal_snapshot():
    store = MemoryStore()
    class Repo:
        calls = 0
        def rows(self, *args, **kwargs):
            self.calls += 1
            assert not kwargs.get('providers')
            return [Transaction(date(2026,1,1),Decimal('100.01'),'revenue','r','revenue')], 'USD'
    repo = Repo()
    for allowed in (False, True):
        app = create_app(Settings('postgresql://unused'), store,
            simulation_config=SimulationConfig(authorized_user_ids=[store.user['user_id']]),
            analytics_config=AnalyticsConfig(authorized_user_ids=[store.user['user_id']] if allowed else []),
            analytics_repo=repo)
        with TestClient(app) as client:
            url='/api/v1/simulations/baseline?start=2026-01-01&end=2026-01-31'
            assert client.get(url).status_code == 401
            _, headers=login(client)
            response=client.get(url,headers=headers)
            assert response.status_code == (200 if allowed else 403)
            if allowed:
                assert response.json()['existing_monthly_revenue'] == '100.01'
                assert client.get(url.replace('2026-01-31','2026-01-15'),headers=headers).status_code == 422
            else:
                assert repo.calls == 0
