from dataclasses import replace
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID
from typing import Literal
from .revenue import revenue_report
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from .calculations import analytics,provider_contributions,check_range
from .config import load_config
from .repository import AnalyticsRepository,DataUnavailable
from .schemas import DashboardResponse,MetadataResponse,ProvidersResponse


def json_exact(value):
    """Do not let FastAPI's default Decimal encoder produce binary floats."""
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,(date,datetime)): return value.isoformat()
    if isinstance(value,UUID): return str(value)
    if isinstance(value,dict): return {str(k):json_exact(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [json_exact(v) for v in value]
    return value


def router(settings,current_user,store,config=None,repo=None):
    config=config or load_config(settings.analytics_config_path)
    repo=repo or AnalyticsRepository(settings)
    api=APIRouter(prefix='/api/v1/analytics')

    def authorize(request,user,compensation=False):
        if not config.permits(user['user_id'],compensation):
            store.audit(user['user_id'],'analytics.denied','providers' if compensation else 'dashboard',request.state.request_id,'denied')
            raise HTTPException(403)

    def error(request,exc):
        return JSONResponse(status_code=422,content={'error':{'code':exc.code,'message':str(exc),
                                                           'request_id':request.state.request_id}})

    def validate_range(start,end):
        try: check_range(start,end)
        except ValueError: raise HTTPException(422) from None

    @api.get('/config')
    def options(request:Request,user=Depends(current_user)):
        store.audit(user['user_id'],'analytics.config','analytics',request.state.request_id)
        return {'enabled':config.permits(user['user_id']),
                'provider_access':config.permits(user['user_id'],True),'synthetic_data':config.synthetic_data}

    @api.get('/metadata',response_model=MetadataResponse)
    def metadata(request:Request,user=Depends(current_user)):
        authorize(request,user)
        return JSONResponse(content=json_exact(repo.metadata(user['user_id'],request.state.request_id)))

    @api.get('/dashboard',response_model=DashboardResponse)
    def dashboard(request:Request,start:date,end:date,clinic_location:str|None=None,user=Depends(current_user)):
        authorize(request,user); validate_range(start,end)
        try: rows,currency=repo.rows(user['user_id'],request.state.request_id,start,end,**({'clinic_location':clinic_location} if clinic_location else {}))
        except DataUnavailable as exc: return error(request,exc)
        approved={str(key):label for key,label in config.public_category_labels.items()}
        labels={**approved,'other_fixed_cost':'Other fixed expenses','other_variable_cost':'Other variable expenses'}
        public=[]
        for row in rows:
            key=row.category_key if row.category_key in approved else ('revenue' if row.type=='revenue' else 'other_'+row.category_type)
            public.append(replace(row,category_key=key,provider_key=None))
        result=analytics(public,start,end)
        result.update(currency=currency,category_labels=labels)
        return JSONResponse(content=json_exact(result))

    @api.get('/providers',response_model=ProvidersResponse)
    def providers(request:Request,start:date,end:date,clinic_location:str|None=None,user=Depends(current_user)):
        authorize(request,user,True); validate_range(start,end)
        try: rows,currency=repo.rows(user['user_id'],request.state.request_id,start,end,providers=True,**({'clinic_location':clinic_location} if clinic_location else {}))
        except DataUnavailable as exc: return error(request,exc)
        result=provider_contributions(rows,start,end,config.coverage())
        labels={str(key):value for key,value in config.provider_labels.items()}
        for item in result['providers']:
            item['label']=labels.get(item['provider_key'],'Provider '+item['provider_key'][:8])
        # The protected response needs unattributed totals, not category identities.
        result['unattributed'].pop('categories',None)
        result['currency']=currency
        return JSONResponse(content=json_exact(result))

    @api.get('/revenue')
    def revenue(request:Request,start:date,end:date,frequency:Literal['week','month','quarter']='month',
                medical_insurance:str|None=None,billing_code:str|None=None,category:str|None=None,clinic_location:str|None=None,user=Depends(current_user)):
        authorize(request,user); validate_range(start,end)
        try: rows,currency=repo.revenue_rows(user['user_id'],request.state.request_id,start,end,**({'clinic_location':clinic_location} if clinic_location else {}))
        except DataUnavailable as exc: return error(request,exc)
        approved={str(key):label for key,label in config.public_category_labels.items()}
        public=[{**r,'category':approved.get(str(r['category_key']),'Other revenue')} for r in rows]
        result=revenue_report(public,start,end,frequency,{'medical_insurance':medical_insurance,
            'billing_code':billing_code,'category':category})
        result['currency']=currency
        return JSONResponse(content=json_exact(result))

    @api.get('/locations')
    def locations(request:Request,start:date,end:date,user=Depends(current_user)):
        authorize(request,user); validate_range(start,end)
        return JSONResponse(content=json_exact({'rows':repo.locations(user['user_id'],request.state.request_id,start,end)}))

    return api
