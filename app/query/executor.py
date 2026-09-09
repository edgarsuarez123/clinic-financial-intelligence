"""The LLM query path has its own restricted PostgreSQL connection, never app credentials."""
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .catalog import CATALOG,Unreliable,validate_result

class ReadOnlyExecutor:
    def __init__(self,dsn): self.dsn=dsn
    @contextmanager
    def connect(self):
        if not self.dsn: raise Unreliable('Read-only database connection is not configured')
        with psycopg.connect(self.dsn,row_factory=dict_row,connect_timeout=5,
                options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000') as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            role=conn.execute('''SELECT current_user AS name,rolsuper,rolcreatedb,rolcreaterole,
                EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS memberships
                FROM pg_roles r WHERE rolname=current_user''').fetchone()
            if role['name']!='clinic_query' or any(role[k] for k in ('rolsuper','rolcreatedb','rolcreaterole','memberships')):
                raise Unreliable('Query connection must use the isolated clinic_query role without role memberships')
            yield conn
    def revision(self):
        with self.connect() as c:
            return c.execute('SELECT revision FROM core.analytics_revision WHERE singleton').fetchone()['revision']
    def execute(self,query,params,expected_revision):
        if CATALOG.get(query.key)!=query: raise Unreliable('Unregistered query')
        with self.connect() as c:
            revision=c.execute('SELECT revision FROM core.analytics_revision WHERE singleton').fetchone()['revision']
            if revision!=expected_revision: raise Unreliable('Financial data changed during translation; submit the question again')
            invalid=c.execute('''SELECT count(DISTINCT currency) AS currencies,
                coalesce(bool_or(currency IS NULL OR invalid_classification),false) AS invalid
                FROM analytics.nl_data_quality WHERE full_date BETWEEN %(start)s AND %(end)s''',params).fetchone()
            if invalid['invalid'] or invalid['currencies']>1: raise Unreliable('Missing/mixed currency or inconsistent category classification')
            # The statement is from the immutable code catalog; values are bound separately.
            rows=c.execute(query.sql,params).fetchmany(101)
            validate_result(query,rows)
            return rows
