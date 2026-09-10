from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
import psycopg
from pydantic import ValidationError
from .catalog import allowed_catalog,validate_sql,validate_result,render_explanation,LABELS,Unreliable
from .schemas import Translation,Explanation
from .provider import ProviderUnavailable
from ..analytics.routes import json_exact

REFUSAL="I can’t answer that reliably."

def strict_json(content):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate JSON keys')
            result[key]=value
        return result
    def constant(value): raise ValueError('Nonfinite JSON number')
    value=json.loads(content,object_pairs_hook=pairs,parse_constant=constant)
    if not isinstance(value,dict): raise ValueError('JSON object required')
    return value

class QueryService:
    def __init__(self,config,repo,executor,provider):
        self.config=config;self.repo=repo;self.executor=executor;self.provider=provider
    def ask(self,body,actor,rid,provider_access):
        config=self.config;repo=self.repo
        key,allowed=repo.begin(actor,rid,body.question,config)
        if not allowed:
            return 429,{'status':'rate_limited','answer':'The clinic query limit has been reached. Try again after the configured rate window resets.'}
        generated_sql=None;params=None;rows=None;query=None
        try:
            revision=self.executor.revision()
            catalog=[asdict(q) for q in allowed_catalog(provider_access)]
            cache_key=hashlib.sha256(json.dumps({'question':body.model_dump(mode='json'),'actor':str(actor),
                'provider_access':provider_access,'revision':revision,'config':config.model_dump(mode='json'),
                'catalog':catalog,'protocol_version':3},sort_keys=True).encode()).hexdigest()
            cached=repo.cache(cache_key,actor,rid)
            if cached:
                repo.finish(key,actor,rid,'cached',cached['sql'],cached['parameters'],cache_hit=True)
                return 200,{**cached,'cached':True}
            completion=self.complete(key,actor,rid,'translate',{'question':body.question,'selected_dates':{
                'start':body.start.isoformat(),'end':body.end.isoformat()},'catalog':catalog})
            decoded=strict_json(completion.content)
            if isinstance(decoded.get('sql'),str): generated_sql=decoded['sql'][:6000]
            translation=Translation.model_validate(decoded)
            params=translation.parameters
            if not translation.answerable or translation.confidence<config.minimum_confidence:
                raise Unreliable('Translation is unsupported, ambiguous or below the configured confidence threshold')
            query,bound=validate_sql(translation.query_key,translation.sql,translation.parameters,body.start,body.end,provider_access)
            repo.record_sql(key,actor,rid,query.sql,params)
            rows=json_exact(self.executor.execute(query,bound,revision))
            validate_result(query,rows)
            explanation_fallback=False
            if rows:
                try:
                    completion=self.complete(key,actor,rid,'explain',{'question':body.question,'query_description':query.description,
                        'sql':query.sql,'parameters':params,'rows':rows,'allowed_metric_columns':[c for c in query.columns if c in LABELS]})
                    explanation=Explanation.model_validate(strict_json(completion.content))
                    facts=[fact.model_dump() for fact in explanation.facts]
                    render_explanation(facts,query,rows)
                except (ProviderUnavailable,ValidationError,ValueError):
                    # A failed narration must not discard a validated database result.
                    facts=[{'row':i,'column':c} for i in range(len(rows)) for c in query.columns if c in LABELS][:20]
                    explanation_fallback=True
            else: facts=[]
            answer=render_explanation(facts,query,rows)
            response={'status':'answered','answer':answer,'query_key':query.key,'interpretation':query.description,
                'sql':query.sql,'parameters':params,'rows':rows,'cached':False,'data_revision':revision,
                'explanation_fallback':explanation_fallback,
                'as_of':datetime.now(timezone.utc).isoformat(),'facts':facts,
                'limitations':'Recorded observations only. Missing periods are not imputed as zero; selected boundary periods may be partial. Provider costs are not certified as fully loaded. Check the displayed interpretation, SQL and values.'}
            repo.finish(key,actor,rid,'answered',generated_sql,params,response,cache_key,config.cache_seconds)
            return 200,response
        except (Unreliable,ValidationError,ValueError):
            repo.finish(key,actor,rid,'refused',generated_sql,params)
            return 200,{'status':'refused','answer':REFUSAL,
                'detail':'The question, SQL, data quality or explanation did not meet the supported query contract. Review the selected dates or use the dashboard.',
                'sql':generated_sql,'parameters':params,'rows':rows}
        except (ProviderUnavailable,psycopg.Error):
            repo.finish(key,actor,rid,'unavailable',generated_sql,params)
            return 503,{'status':'unavailable','answer':'Financial questions are temporarily unavailable. Dashboards and saved budgets can still be used.',
                       'sql':generated_sql,'parameters':params,'rows':rows}
    def complete(self,key,actor,rid,task,payload):
        try: result=self.provider.complete(task,payload)
        except ProviderUnavailable:
            self.repo.usage(key,actor,rid,task,None)
            raise
        # Record billable usage before parsing or validating model content.
        self.repo.usage(key,actor,rid,task,result)
        return result
