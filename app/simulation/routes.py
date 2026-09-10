from uuid import UUID
from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from fastapi.responses import JSONResponse
from .schemas import PlanInput,CreateBudget,UpdateBudget
from .config import load_config
from .service import calculate
from .repository import BudgetRepository,BudgetConflict,BudgetMissing
from ..analytics.config import load_config as analytics_config_load
from ..analytics.repository import AnalyticsRepository,DataUnavailable
from ..analytics.routes import json_exact

def router(settings,current_user,store,config=None,analytics_config=None,repo=None,budget_repo=None):
    config=config or load_config(settings.simulation_config_path)
    access=analytics_config or analytics_config_load(settings.analytics_config_path)
    repo=repo or AnalyticsRepository(settings)
    budgets=budget_repo or BudgetRepository(settings)
    api=APIRouter(prefix='/api/v1/simulations')

    def authorize(request,user,body=None):
        historical=body is not None and any(s.revenue.kind=='historical' for s in body.staff)
        if not config.permits(user['user_id']) or (historical and not access.permits(user['user_id'],True)):
            store.audit(user['user_id'],'simulation.denied','simulation',request.state.request_id,'denied')
            raise HTTPException(403)

    def reject(request,user,exc):
        store.audit(user['user_id'],'simulation.rejected','simulation',request.state.request_id,'error')
        return JSONResponse(status_code=422,content={'error':{'code':'invalid_simulation','message':str(exc),'request_id':request.state.request_id}})

    def budget_error(request,exc):
        if isinstance(exc,BudgetMissing): raise HTTPException(404)
        return JSONResponse(status_code=409,content={'error':{'code':'budget_conflict',
            'message':'This budget changed since you opened it. Reopen the latest version or save your edits as a new budget.',
            'request_id':request.state.request_id}})

    def document(row):
        return {k:row[k] for k in ('budget_id','name','revision','plan','result','model_version','created_at','updated_at')}

    @api.get('/config')
    def options(request:Request,user=Depends(current_user)):
        store.audit(user['user_id'],'simulation.config','simulation',request.state.request_id)
        return {'enabled':config.permits(user['user_id']),'synthetic_data':config.synthetic_data,
                'historical_access':access.permits(user['user_id'],True)}

    @api.post('/clinic')
    def simulate(body:PlanInput,request:Request,user=Depends(current_user)):
        authorize(request,user,body)
        try: result=calculate(body,repo,user['user_id'],request.state.request_id)
        except (ValueError,DataUnavailable) as exc: return reject(request,user,exc)
        store.audit(user['user_id'],'simulation.calculate','simulation',request.state.request_id)
        return JSONResponse(content=json_exact(result))

    @api.get('/baseline')
    def baseline(request:Request,start:date,end:date,clinic_location:str|None=None,user=Depends(current_user)):
        authorize(request,user)
        if not access.permits(user['user_id']):
            store.audit(user['user_id'],'simulation.baseline.denied','simulation',request.state.request_id,'denied')
            raise HTTPException(403)
        from .baseline import clinic_baseline
        from ..analytics.calculations import check_range
        try:
            check_range(start,end)
            rows,currency=repo.rows(user['user_id'],request.state.request_id,start,end,**({'clinic_location':clinic_location} if clinic_location else {}))
            result=clinic_baseline(rows,start,end,{str(k):v for k,v in access.public_category_labels.items()})
            result['basis']+=' Location: '+(clinic_location or 'All clinics')+'.'
        except (ValueError,DataUnavailable) as exc: return reject(request,user,exc)
        return JSONResponse(content=json_exact({**result,'currency':currency}))

    @api.get('/budgets')
    def list_budgets(request:Request,offset:int=Query(0,ge=0,le=100000),user=Depends(current_user)):
        authorize(request,user)
        return JSONResponse(content=json_exact(budgets.list(user['user_id'],request.state.request_id,access.permits(user['user_id'],True),offset)))

    @api.get('/budgets/{budget_id}')
    def get_budget(budget_id:UUID,request:Request,user=Depends(current_user)):
        authorize(request,user)
        try: row=budgets.get(budget_id,user['user_id'],request.state.request_id,access.permits(user['user_id'],True))
        except BudgetMissing as exc: return budget_error(request,exc)
        return JSONResponse(content=json_exact(document(row)))

    def save(body,budget_id,revision,request,user):
        authorize(request,user,body.plan)
        provider_access=access.permits(user['user_id'],True)
        try:
            if revision is not None:
                # Check ownership before resolving any new history or doing calculation work.
                budgets.get(budget_id,user['user_id'],request.state.request_id,provider_access)
            result=calculate(body.plan,repo,user['user_id'],request.state.request_id)
            row=budgets.save(budget_id,user['user_id'],request.state.request_id,body.name,
                body.plan.model_dump(mode='json'),json_exact(result),provider_access,revision)
        except (BudgetMissing,BudgetConflict) as exc: return budget_error(request,exc)
        except (ValueError,DataUnavailable) as exc: return reject(request,user,exc)
        return JSONResponse(content=json_exact(document(row)))

    @api.post('/budgets')
    def create_budget(body:CreateBudget,request:Request,user=Depends(current_user)):
        return save(body,body.budget_id,None,request,user)

    @api.put('/budgets/{budget_id}')
    def update_budget(budget_id:UUID,body:UpdateBudget,request:Request,user=Depends(current_user)):
        return save(body,budget_id,body.expected_revision,request,user)
    return api
