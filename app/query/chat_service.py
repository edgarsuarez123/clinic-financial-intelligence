"""Conversation orchestration with validated tools, Decimal results and cited inference."""
import hashlib
import json
import re
from datetime import date,datetime,timezone
from decimal import Decimal
from dataclasses import asdict
from .chat_schemas import ChatSelection,ChatNarrative
from .chat_catalog import CHAT_CATALOG
from .chat_tools import apply_changes
from .service import strict_json
from .provider import ProviderUnavailable
from .catalog import Unreliable,validate_result
from ..analytics.routes import json_exact
from ..analytics.calculations import exact
from ..simulation.service import calculate
from ..simulation.forecast import forecast_months
from ..simulation.repository import BudgetMissing

METRICS={'revenue','expense','net','margin_pct','total_revenue','total_cost','lower_80','upper_80','net_change','fixed_cost','variable_cost','fixed_cost_pct','variable_cost_pct','revenue_cv','expense_cv','observed_weeks','recorded_cost','observed_net'}

@exact
def facts_for(tables):
    facts=[]
    for ti,table in enumerate(tables):
        for ri,row in enumerate(table['rows']):
            context=' · '.join(str(row[k]) for k in ('plan','scenario','period','medical_insurance','billing_code','clinic_location','provider_key') if k in row)
            for col in table['columns']:
                if col in METRICS and row.get(col) is not None:
                    value=Decimal(str(row[col]))
                    facts.append({'id':f'f{ti}_{ri}_{col}','label':f'{context+": " if context else ""}{col.replace("_"," ")}',
                        'value':format(value.quantize(Decimal('.01')),'f'),'unit':'%' if col.endswith('_pct') else '' if col in {'revenue_cv','expense_cv','observed_weeks'} else row.get('currency',table.get('currency',''))})
    return facts[:160]

def validated_narrative(raw,facts,want_recommendations):
    value=ChatNarrative.model_validate(strict_json(raw));by_id={f['id']:f for f in facts}
    result={'interpretation':[],'recommendations':[]}
    for group in result:
        if group=='recommendations' and not want_recommendations: continue
        for item in getattr(value,group):
            if not all(ref in by_id for ref in item.evidence): raise ValueError('Unverified evidence reference')
            # Numeric claims must use returned fact placeholders, not model-authored amounts.
            refs=re.findall(r'\{\{([^{}]+)\}\}',item.text)
            if not all(ref in item.evidence for ref in refs): raise ValueError('Uncited numeric placeholder')
            prose=re.sub(r'\{\{[^{}]+\}\}','',item.text)
            if any(c.isnumeric() for c in prose) or any(c in prose for c in '{}$€£%'): raise ValueError('Unverified number in interpretation')
            text=item.text
            for ref in refs: text=text.replace('{{'+ref+'}}',by_id[ref]['value']+' '+by_id[ref]['unit'])
            result[group].append({'text':text,'evidence':item.evidence})
    return result

class ChatService:
    def __init__(self,query_service,budgets,analytics_repo):
        self.query=query_service;self.budgets=budgets;self.analytics=analytics_repo

    @exact
    def ask(self,body,history,actor,rid,provider_access,simulation_access,protect=lambda *_:None):
        q=self.query;log_id,allowed=q.repo.begin(actor,rid,body.question,q.config)
        if not allowed: return {'status':'rate_limited','answer':'The clinic question limit has been reached. Please try again later.'}
        sources=[];provider_required=False;simulation_required=False
        try:
            available=self.budgets.list(actor,rid,provider_access)['budgets'] if simulation_access else []
            selected=[]
            for key in body.context.budget_ids:
                if not simulation_access: raise BudgetMissing()
                selected.append(self.budgets.get(key,actor,rid,provider_access))
            if selected:
                protect(any(p['requires_provider_access'] for p in selected),True)
            payload={'question':body.question,'context':body.context.model_dump(mode='json'),
                'history':[{'question':t['question'],'answer':(t.get('response') or {}).get('answer',''),
                    'context':t.get('context',{}),'facts':(t.get('response') or {}).get('facts',[])[:30],
                    'sources':(t.get('response') or {}).get('sources',[])} for t in history[-8:] if t['status']!='running'],
                'catalog':[{'key':x.key,'description':x.description} for x in CHAT_CATALOG.values() if provider_access or not x.provider_access],
                'saved_plans':json_exact([{'budget_id':p['budget_id'],'name':p['name'],'revision':p['revision']} for p in available]),
                'selected_plans':json_exact([{'budget_id':p['budget_id'],'name':p['name'],'revision':p['revision'],'plan':p['plan']} for p in selected])}
            selection=ChatSelection.model_validate(strict_json(q.complete(log_id,actor,rid,'chat_plan',payload).content))
            if selection.confidence<q.config.minimum_confidence or selection.tool=='clarify':
                raise Unreliable('Please specify the financial measure, dates or saved plan you want to analyze.')
            tables=[];draft=None;forecast=None;diagnostics={};cache_hit=False
            if selection.tool in {'analytics','forecast'}:
                if selection.budget_ids or selection.changes: raise Unreliable('This request mixes incompatible tools.')
                query=CHAT_CATALOG.get('monthly' if selection.tool=='forecast' else selection.query_key)
                if not query: raise Unreliable('That financial breakdown is not supported yet.')
                if query.provider_access:
                    if not provider_access: raise BudgetMissing()
                    provider_required=True;protect(True,False)
                params={'start':body.context.start,'end':body.context.end,'clinic_location':body.context.clinic_location or None}
                revision=q.executor.revision()
                cache_key=hashlib.sha256(json.dumps({'chat_tool':2,'actor':str(actor),'query':query.key,'params':json_exact(params),'revision':revision},sort_keys=True).encode()).hexdigest()
                cached=q.repo.cache(cache_key,actor,rid)
                cache_hit=bool(cached)
                rows=cached['rows'] if cached else json_exact(q.executor.execute_chat(query,params,revision))
                validate_result(query,rows)
                q.repo.record_sql(log_id,actor,rid,query.sql,json_exact(params))
                diagnostics={'sql':query.sql,'parameters':json_exact(params),'data_revision':revision}
                sources=[{'kind':'actuals','start':body.context.start.isoformat(),'end':body.context.end.isoformat(),
                    'clinic_location':body.context.clinic_location,'data_revision':revision}]
                if selection.tool=='forecast':
                    from ..simulation.calculations import anniversary
                    if body.context.start.day!=1 or anniversary(body.context.end.replace(day=1),1).toordinal()!=body.context.end.toordinal()+1:
                        raise ValueError('Forecast history must start and end on complete calendar-month boundaries.')
                    forecast=forecast_months(rows,selection.horizon,date.today())
                    tables=[{'title':'History-based revenue forecast','rows':[{**r,'currency':rows[0]['currency']} for r in forecast['periods']],
                        'columns':['period','currency','revenue','lower_80','upper_80'],'x':'period','keys':['revenue','lower_80','upper_80'],'chart':'line'}]
                else:
                    x=next((c for c in query.columns if c in {'period','medical_insurance','billing_code','clinic_location','provider_key'}),'currency')
                    tables=[{'title':query.description,'rows':rows,'columns':list(query.columns),'x':x,
                        'keys':[c for c in ('revenue','expense','net','fixed_cost','variable_cost','recorded_cost','observed_net') if c in query.columns],
                        'chart':selection.visualization if selection.visualization!='auto' else 'line' if x=='period' else 'bar'}]
                # Cache only validated actuals, never permission-bearing plan snapshots or generated text.
                q.repo.finish(log_id,actor,rid,'answered',query.sql,json_exact(params),{'rows':rows},cache_key,q.config.cache_seconds,cache_hit=bool(cached))
            else:
                if not simulation_access: raise BudgetMissing()
                ids=selection.budget_ids or body.context.budget_ids
                if not ids: raise Unreliable('Choose a saved plan, or name the plan you want to compare.')
                if len(set(ids))!=len(ids): raise Unreliable('Choose distinct plans.')
                plans=[self.budgets.get(key,actor,rid,provider_access) for key in ids]
                provider_required=any(p['requires_provider_access'] for p in plans);simulation_required=True
                protect(provider_required,True)
                if len({(p['plan']['currency'],p['plan']['start_date'],p['plan']['months']) for p in plans})!=1:
                    raise ValueError('Compare plans with the same currency, start date and horizon.')
                for p in plans: sources.append({'kind':'saved_plan','budget_id':str(p['budget_id']),'name':p['name'],'revision':p['revision']})
                if selection.tool=='what_if':
                    if len(plans)!=1: raise ValueError('Select one saved plan for a what-if draft.')
                    if str(ids[0]) not in {str(k) for k in body.context.budget_ids}: raise ValueError('Attach the saved plan before asking for row-specific changes.')
                    edited=apply_changes(plans[0]['plan'],selection.changes)
                    computed=calculate(edited,self.analytics,actor,rid)
                    draft={'name':(plans[0]['name']+' · proposed changes')[:100],'plan':edited.model_dump(mode='json'),
                        'source':sources[0],'changes':[c.model_dump(mode='json') for c in selection.changes],
                        'history_refreshed':any(s.revenue.kind=='historical' for s in edited.staff)}
                    if draft['history_refreshed']:
                        for staff in edited.staff:
                            if staff.revenue.kind=='historical':
                                sources.append({'kind':'actuals','start':staff.revenue.start.isoformat(),'end':staff.revenue.end.isoformat(),
                                    'clinic_location':None,'use':'Refreshed provider revenue baseline for proposed plan'})
                    plans.append({'name':draft['name'],'plan':draft['plan'],'result':json_exact(computed)})
                elif selection.changes: raise Unreliable('Edits require an explicit what-if request.')
                rows=[]
                for p in plans:
                    for s in p['result']['scenarios']:
                        rows.append({'label':p['name']+' · '+s['scenario'],'plan':p['name'],'scenario':s['scenario'],'currency':p['plan']['currency'],
                            **{k:s['summary'].get(k) for k in ('total_revenue','total_cost','net','margin_pct')}})
                tables=[{'title':'Scenario comparison','rows':rows,'columns':['plan','scenario','currency','total_revenue','total_cost','net','margin_pct'],
                    'x':'label','keys':['total_revenue','total_cost','net'],'chart':'bar' if selection.visualization=='bar' else 'table'}]
                # Same dates/horizon/currency checked above: exact month-by-month deltas are meaningful.
                base=plans[0]['result']['scenarios'];base_expected=next(s for s in base if s['scenario']=='expected')
                for p in plans:
                    s=next(s for s in p['result']['scenarios'] if s['scenario']=='expected')
                    monthly=[{'period':r['start'],'currency':p['plan']['currency'],'revenue':r['revenue'],'expense':r['total_cost'],'net':r['net'],
                        'net_change':format(Decimal(r['net'])-Decimal(base_expected['periods'][i]['net']),'f')} for i,r in enumerate(s['periods'])]
                    tables.append({'title':p['name']+' · base case','rows':monthly,'columns':['period','currency','revenue','expense','net','net_change'],
                        'x':'period','keys':['revenue','expense','net'],'chart':selection.visualization if selection.visualization!='auto' else 'line'})
            facts=facts_for(tables)
            answer=('Proposed changes calculated. Your saved plan has not been changed.' if draft else 'Here is the history-based revenue forecast.' if forecast else 'Here are the saved scenario results.' if simulation_required else 'Here are the recorded results for your selected dates and clinic.') if facts else 'No recorded data was returned for this selection.'
            if draft and draft['history_refreshed']: answer+=' Provider revenue baselines were refreshed for the saved historical dates; differences may also reflect updated imports.'
            narrative={'interpretation':[],'recommendations':[]};fallback=False
            if facts:
                try:
                    narration=q.complete(log_id,actor,rid,'chat_explain',{'question':body.question,'facts':facts,'sources':sources,
                        'recommendations_requested':selection.recommendations,'mode':'projection' if simulation_required or forecast else 'recorded',
                        'instruction':'Separate inference from verified observations; do not assert causation or completeness.'})
                    narrative=validated_narrative(narration.content,facts,selection.recommendations)
                except (ValueError,ProviderUnavailable): fallback=True
            result={'status':'answered','answer':answer,'tables':tables,'facts':facts,'sources':sources,'draft':draft,
                'forecast':forecast,**narrative,'narration_unavailable':fallback,'as_of':datetime.now(timezone.utc).isoformat(),
                'requires_provider_access':provider_required,'requires_simulation_access':simulation_required,**diagnostics}
            q.repo.finish(log_id,actor,rid,'answered',diagnostics.get('sql'),diagnostics.get('parameters'),cache_hit=cache_hit)
            return json_exact(result)
        except BudgetMissing:
            q.repo.finish(log_id,actor,rid,'refused')
            return {'status':'refused','answer':'The requested saved plan is unavailable or not permitted for your account.'}
        except (ValueError,Unreliable) as exc:
            q.repo.finish(log_id,actor,rid,'refused')
            # Never echo a validation exception containing model-supplied input.
            message=str(exc) if type(exc) in {ValueError,Unreliable} else 'The model could not select a reliable calculation. Try specifying the measure and saved plan.'
            return {'status':'refused','answer':message}
        except ProviderUnavailable:
            q.repo.finish(log_id,actor,rid,'unavailable')
            return {'status':'unavailable','answer':'Clarity is temporarily unavailable. Your question is saved; dashboards and budgets still work.'}
