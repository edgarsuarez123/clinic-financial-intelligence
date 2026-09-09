from datetime import date
from decimal import Decimal
from uuid import uuid4
import psycopg
import pytest
from app.analytics.repository import AnalyticsRepository,DataUnavailable
from app.settings import Settings
from test_postgres import db,fact

pytestmark=pytest.mark.integration

@pytest.fixture
def analytics_fact(db,fact):
    with psycopg.connect(db[0]) as c:
        c.execute("UPDATE core.uploads SET status='completed',total_rows=1,rows_accepted=1,currency='USD' WHERE upload_id=%s",(fact[1],))
    return fact

def test_general_view_has_no_provider_or_source_identifiers(db):
    with psycopg.connect(db[1]) as c:
        cur=c.execute('SELECT * FROM analytics.dashboard_facts LIMIT 0')
        names={column.name for column in cur.description}
        assert 'provider_key' not in names and 'source_upload_id' not in names
        assert 'amount' in names

def test_database_decimal_round_trip_and_read_audit(db,analytics_fact):
    with psycopg.connect(db[1]) as c:
        amount=c.execute('SELECT amount FROM analytics.dashboard_facts WHERE category_key=%s',(analytics_fact[2],)).fetchone()[0]
        assert amount==Decimal('.10') and isinstance(amount,Decimal)
    repo=AnalyticsRepository(Settings(db[1])); request_id=uuid4()
    repo.metadata(None,request_id)
    with psycopg.connect(db[0]) as c:
        assert c.execute('SELECT count(*) FROM audit.audit_log WHERE request_id=%s',(request_id,)).fetchone()[0]==1

def test_soft_deleted_upload_is_excluded_from_views(db,analytics_fact):
    with psycopg.connect(db[0]) as c:
        c.execute('UPDATE core.uploads SET deleted_at=now() WHERE upload_id=%s',(analytics_fact[1],))
    with psycopg.connect(db[1]) as c:
        assert c.execute('SELECT count(*) FROM analytics.dashboard_facts WHERE category_key=%s',(analytics_fact[2],)).fetchone()[0]==0

def test_missing_currency_refuses_analytics(db,analytics_fact):
    with psycopg.connect(db[0]) as c:
        c.execute('UPDATE core.uploads SET currency=NULL WHERE upload_id=%s',(analytics_fact[1],))
    repo=AnalyticsRepository(Settings(db[1]))
    with pytest.raises(DataUnavailable) as exc:
        repo.rows(None,uuid4(),date(2026,9,8),date(2026,9,8))
    assert exc.value.code=='currency_unconfirmed'
