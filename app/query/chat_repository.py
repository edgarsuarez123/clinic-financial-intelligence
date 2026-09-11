"""Short audited transactions; no database lock is held during an LLM call."""
import hashlib
import json
from uuid import uuid4
from psycopg.types.json import Jsonb
from ..store import Store
from ..simulation.repository import BudgetMissing, BudgetConflict

class ConversationRepository(Store):
    def protect(self,key,actor,rid,provider_required,simulation_required):
        with self.connect() as c:
            self._get(c,key,actor,True,True,True)
            c.execute('''UPDATE core.conversation SET requires_provider_access=requires_provider_access OR %s,
                requires_simulation_access=requires_simulation_access OR %s WHERE conversation_id=%s''',
                (provider_required,simulation_required,key))
            self._audit(c,actor,'conversation.protect',str(key),rid,'success')

    def _get(self,c,key,actor,provider,simulation,lock=False,include_deleted=False):
        row=c.execute('''SELECT * FROM core.conversation WHERE conversation_id=%s AND owner_id=%s
            AND (NOT requires_provider_access OR %s) AND (NOT requires_simulation_access OR %s)
            AND (deleted_at IS NULL OR %s)'''+(' FOR UPDATE' if lock else ''),
            (key,actor,provider,simulation,include_deleted)).fetchone()
        if row is None: raise BudgetMissing()
        return row

    def list(self,actor,rid,provider,simulation,offset=0):
        with self.connect() as c:
            rows=c.execute('''SELECT conversation_id,title,revision,updated_at FROM core.conversation
                WHERE owner_id=%s AND deleted_at IS NULL AND (NOT requires_provider_access OR %s)
                AND (NOT requires_simulation_access OR %s) ORDER BY updated_at DESC,conversation_id
                LIMIT 51 OFFSET %s''',(actor,provider,simulation,offset)).fetchall()
            self._audit(c,actor,'conversation.list','conversations',rid,'success')
            return {'conversations':rows[:50],'has_more':len(rows)>50}

    def create(self,body,actor,rid):
        with self.connect() as c:
            c.execute('''INSERT INTO core.conversation(conversation_id,owner_id,title) VALUES (%s,%s,%s)
                ON CONFLICT DO NOTHING''',(body.conversation_id,actor,body.title))
            row=self._get(c,body.conversation_id,actor,True,True)
            if row['title']!=body.title or row['revision']!=1: raise BudgetConflict()
            self._audit(c,actor,'conversation.create',str(body.conversation_id),rid,'success')
            return {**row,'turns':[]}

    def get(self,key,actor,rid,provider,simulation):
        with self.connect() as c:
            row=self._get(c,key,actor,provider,simulation)
            turns=c.execute('''SELECT turn_id,position,question,context,response,status FROM core.conversation_turn
                WHERE conversation_id=%s AND deleted_at IS NULL ORDER BY position''',(key,)).fetchall()
            self._audit(c,actor,'conversation.read',str(key),rid,'success')
            return {**row,'turns':turns}

    def change(self,key,actor,rid,provider,simulation,revision,title=None,delete=False):
        with self.connect() as c:
            row=self._get(c,key,actor,provider,simulation,True,delete)
            if row['revision']!=revision:
                if not (delete and row['deleted_at'] and row['revision']==revision+1): raise BudgetConflict()
                return row
            if not row['deleted_at']:
                row=c.execute('''UPDATE core.conversation SET title=coalesce(%s,title),
                    deleted_at=CASE WHEN %s THEN now() ELSE NULL END,revision=revision+1
                    WHERE conversation_id=%s RETURNING *''',(title,delete,key)).fetchone()
            self._audit(c,actor,'conversation.delete' if delete else 'conversation.rename',str(key),rid,'success')
            return row

    def begin(self,key,body,actor,rid,provider,simulation):
        context=body.context.model_dump(mode='json')
        digest=hashlib.sha256(json.dumps({'question':body.question,'context':context},sort_keys=True).encode()).hexdigest()
        with self.connect() as c:
            row=self._get(c,key,actor,provider,simulation,True)
            previous=c.execute('SELECT *, started_at < now()-interval \'6 minutes\' AS expired FROM core.conversation_turn WHERE turn_id=%s',(body.turn_id,)).fetchone()
            if previous:
                if str(previous['conversation_id'])!=str(key) or previous['input_hash']!=digest: raise BudgetConflict()
                if previous['status']!='running': return previous,None
                if not previous['expired']: raise BudgetConflict()
                attempt=uuid4()
                c.execute('UPDATE core.conversation_turn SET attempt_id=%s,started_at=now() WHERE turn_id=%s',(attempt,body.turn_id))
            else:
                if row['revision']!=body.expected_revision: raise BudgetConflict()
                pending=c.execute("SELECT 1 FROM core.conversation_turn WHERE conversation_id=%s AND status='running'",(key,)).fetchone()
                if pending: raise BudgetConflict()
                count=c.execute('SELECT count(*) AS n FROM core.conversation_turn WHERE conversation_id=%s',(key,)).fetchone()['n']
                if count>=100: raise ValueError('This conversation has reached 100 questions. Start a new conversation.')
                attempt=uuid4()
                c.execute('''INSERT INTO core.conversation_turn(turn_id,conversation_id,position,question,context,input_hash,status,attempt_id)
                    VALUES (%s,%s,%s,%s,%s,%s,'running',%s)''',(body.turn_id,key,count+1,body.question,Jsonb(context),digest,attempt))
                c.execute('UPDATE core.conversation SET revision=revision+1 WHERE conversation_id=%s',(key,))
            self._audit(c,actor,'conversation.begin',str(key),rid,'success')
            return None,attempt

    def finish(self,key,turn_id,attempt,actor,rid,response,provider_required,simulation_required):
        with self.connect() as c:
            # Lock parent first consistently with begin/delete; never resurrect a deleted thread.
            row=self._get(c,key,actor,True,True,True)
            changed=c.execute('''UPDATE core.conversation_turn SET response=%s,status=%s
                WHERE turn_id=%s AND conversation_id=%s AND attempt_id=%s AND status='running' RETURNING turn_id''',
                (Jsonb(response),response['status'],turn_id,key,attempt)).fetchone()
            if not changed: raise BudgetConflict()
            c.execute('''UPDATE core.conversation SET requires_provider_access=requires_provider_access OR %s,
                requires_simulation_access=requires_simulation_access OR %s,updated_at=now() WHERE conversation_id=%s''',
                (provider_required,simulation_required,key))
            self._audit(c,actor,'conversation.complete',str(key),rid,'success')
