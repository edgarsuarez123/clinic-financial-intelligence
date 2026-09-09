from uuid import uuid4
from psycopg.types.json import Jsonb
from ..store import Store

class QueryRepository(Store):
    def begin(self,actor,rid,question,config):
        key=uuid4()
        with self.connect() as c:
            row=c.execute('SELECT *,now() AS current_time FROM core.nl_rate_limit WHERE singleton FOR UPDATE').fetchone()
            elapsed=(row['current_time']-row['window_start']).total_seconds()
            if elapsed>=config.window_seconds:
                c.execute('UPDATE core.nl_rate_limit SET attempts=0,window_start=now() WHERE singleton')
                row['attempts']=0
            allowed=row['attempts']<config.requests_per_window
            if allowed: c.execute('UPDATE core.nl_rate_limit SET attempts=attempts+1 WHERE singleton')
            c.execute('''INSERT INTO core.query_log(query_id,actor,question,execution_outcome,input_tokens,output_tokens,
                token_cost,llm_provider,llm_model,request_id,input_price_per_million,output_price_per_million,pricing_currency)
                VALUES (%s,%s,%s,%s,0,0,0,%s,%s,%s,%s,%s,%s)''',
                (key,actor,question,'running' if allowed else 'rate_limited',config.provider_name,config.model,rid,
                 config.input_price_per_million,config.output_price_per_million,config.pricing_currency))
            self._audit(c,actor,'query.begin' if allowed else 'query.rate_limited',str(key),rid,'success' if allowed else 'denied')
        return key,allowed
    def usage(self,key,actor,rid,task,completion=None):
        it=completion.input_tokens if completion else None;ot=completion.output_tokens if completion else None
        unknown=it is None or ot is None
        detail={'task':task,'input_tokens':it,'output_tokens':ot,'reported_model':completion.reported_model if completion else None}
        with self.connect() as c:
            c.execute('''UPDATE core.query_log SET input_tokens=input_tokens+%s,output_tokens=output_tokens+%s,
                token_cost=token_cost+(%s*input_price_per_million+%s*output_price_per_million)/1000000,
                unknown_usage_calls=unknown_usage_calls+%s,usage_detail=usage_detail||%s
                WHERE query_id=%s AND actor=%s''',(it or 0,ot or 0,it or 0,ot or 0,int(unknown),Jsonb([detail]),key,actor))
            self._audit(c,actor,'query.usage',str(key),rid,'success')
    def record_sql(self,key,actor,rid,sql,params):
        with self.connect() as c:
            c.execute('UPDATE core.query_log SET generated_sql=%s,parameters=%s WHERE query_id=%s AND actor=%s',
                (sql,Jsonb(params),key,actor))
            self._audit(c,actor,'query.execute',str(key),rid,'success')
    def cache(self,key,actor,rid):
        with self.connect() as c:
            row=c.execute('SELECT payload FROM core.query_cache WHERE cache_key=%s AND actor=%s AND expires_at>now() AND deleted_at IS NULL',(key,actor)).fetchone()
            self._audit(c,actor,'query.cache_read',key,rid,'success')
            return row['payload'] if row else None
    def finish(self,key,actor,rid,outcome,sql=None,params=None,response=None,cache_key=None,cache_seconds=300,cache_hit=False):
        with self.connect() as c:
            c.execute('''UPDATE core.query_log SET execution_outcome=%s,generated_sql=%s,parameters=%s,cache_hit=%s
                WHERE query_id=%s AND actor=%s''',(outcome,sql,Jsonb(params) if params else None,cache_hit,key,actor))
            if cache_key and response:
                c.execute('''INSERT INTO core.query_cache(cache_key,actor,payload,expires_at)
                    VALUES (%s,%s,%s,now()+%s*interval '1 second')
                    ON CONFLICT(cache_key) DO UPDATE SET payload=EXCLUDED.payload,expires_at=EXCLUDED.expires_at,deleted_at=NULL''',
                    (cache_key,actor,Jsonb(response),cache_seconds))
            self._audit(c,actor,'query.'+outcome,str(key),rid,'success' if outcome in {'answered','cached'} else 'error')
    def costs(self,actor,rid,start,end):
        with self.connect() as c:
            rows=c.execute('''SELECT pricing_currency,count(*) AS requests,count(*) FILTER (WHERE cache_hit) AS cache_hits,
                sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens,sum(token_cost) AS estimated_known_cost,
                sum(unknown_usage_calls) AS unknown_usage_calls,count(*) FILTER(WHERE execution_outcome='running') AS incomplete_requests
                FROM core.query_log WHERE deleted_at IS NULL AND created_at >= %s::date AND created_at < %s::date+1
                GROUP BY pricing_currency ORDER BY pricing_currency''',(start,end)).fetchall()
            self._audit(c,actor,'query.costs','clinic-query-costs',rid,'success')
            return rows
