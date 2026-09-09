"""Durable budget documents; all reads/writes audit in the same transaction."""
import hashlib
import json
from psycopg.types.json import Jsonb
from ..store import Store

MODEL_VERSION='clinic-budget-1'
class BudgetConflict(Exception): pass
class BudgetMissing(Exception): pass

def input_hash(name,plan):
    return hashlib.sha256(json.dumps({'name':name,'plan':plan},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def visible(row,actor,provider_access):
    return row and str(row['owner_id'])==str(actor) and not row['deleted_at'] and (provider_access or not row['requires_provider_access'])

class BudgetRepository(Store):
    def list(self,actor,rid,provider_access,offset=0):
        with self.connect() as conn:
            rows=conn.execute("""SELECT budget_id,name,revision,created_at,updated_at,model_version
                FROM core.saved_budget WHERE owner_id=%s AND deleted_at IS NULL
                AND (NOT requires_provider_access OR %s)
                ORDER BY updated_at DESC,budget_id LIMIT 51 OFFSET %s""",(actor,provider_access,offset)).fetchall()
            self._audit(conn,actor,'budget.list','budgets',rid,'success')
            return {'budgets':rows[:50],'has_more':len(rows)>50}

    def get(self,budget_id,actor,rid,provider_access):
        with self.connect() as conn:
            row=conn.execute("SELECT * FROM core.saved_budget WHERE budget_id=%s AND owner_id=%s AND deleted_at IS NULL AND (NOT requires_provider_access OR %s)",(budget_id,actor,provider_access)).fetchone()
            if not visible(row,actor,provider_access):
                self._audit(conn,actor,'budget.denied',str(budget_id),rid,'denied')
                missing=True
            else:
                self._audit(conn,actor,'budget.read',str(budget_id),rid,'success')
                missing=False
        if missing: raise BudgetMissing()
        return row

    def save(self,budget_id,actor,rid,name,plan,result,provider_access,expected_revision=None):
        digest=input_hash(name,plan)
        historical=any(s['revenue']['kind']=='historical' for s in plan['staff'])
        conflict=False; missing=False
        with self.connect() as conn:
            if expected_revision is None:
                inserted=conn.execute("""INSERT INTO core.saved_budget
                    (budget_id,owner_id,name,plan,result,model_version,requires_provider_access,input_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *""",
                    (budget_id,actor,name,Jsonb(plan),Jsonb(result),MODEL_VERSION,historical,digest)).fetchone()
                if inserted:
                    self._audit(conn,actor,'budget.create',str(budget_id),rid,'success')
                    return inserted
            row=conn.execute("SELECT * FROM core.saved_budget WHERE budget_id=%s AND owner_id=%s AND deleted_at IS NULL AND (NOT requires_provider_access OR %s) FOR UPDATE",(budget_id,actor,provider_access)).fetchone()
            if not visible(row,actor,provider_access): missing=True
            elif expected_revision is None:
                # A retransmission can return the original create only, not an unrelated later revision.
                if row['revision']!=1 or row['input_hash']!=digest: conflict=True
            elif row['revision']!=expected_revision:
                # Exact retry after a successful update is safe, including after a lost response.
                if row['revision']!=expected_revision+1 or row['input_hash']!=digest: conflict=True
            else:
                row=conn.execute("""UPDATE core.saved_budget SET name=%s,plan=%s,result=%s,
                    model_version=%s,requires_provider_access=%s,input_hash=%s,revision=revision+1
                    WHERE budget_id=%s RETURNING *""",
                    (name,Jsonb(plan),Jsonb(result),MODEL_VERSION,historical,digest,budget_id)).fetchone()
            self._audit(conn,actor,'budget.denied' if missing else ('budget.conflict' if conflict else 'budget.save'),
                        str(budget_id),rid,'denied' if missing else ('error' if conflict else 'success'))
        if missing: raise BudgetMissing()
        if conflict: raise BudgetConflict()
        return row
