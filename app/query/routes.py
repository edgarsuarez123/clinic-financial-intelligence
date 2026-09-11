from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from .config import load_config
from .schemas import Question
from .catalog import allowed_catalog
from .repository import QueryRepository
from .executor import ReadOnlyExecutor
from .provider import HTTPSChatProvider,DemoProvider,OllamaProvider,DEMO_QUESTIONS
from .service import QueryService
from ..analytics.config import load_config as analytics_config_load
from ..analytics.calculations import check_range
from ..analytics.routes import json_exact

def router(settings,current_user,store,config=None,analytics_config=None,repo=None,executor=None,provider=None,simulation_config=None,budget_repo=None,analytics_repo=None,conversation_repo=None):
    config=config or load_config(settings.query_config_path)
    analytics=analytics_config or analytics_config_load(settings.analytics_config_path)
    repo=repo or QueryRepository(settings)
    executor=executor or ReadOnlyExecutor(settings.query_database_url)
    if config.transport in {"demo","ollama"} and settings.app_environment not in {"dev","test"}:
        raise ValueError("Demo question provider is forbidden outside dev/test")
    provider=provider or (DemoProvider() if config.transport=="demo" else OllamaProvider(config) if config.transport=="ollama" else HTTPSChatProvider(config,settings.llm_api_key))
    service=QueryService(config,repo,executor,provider)
    api=APIRouter(prefix='/api/v1/questions')
    def authorized(user): return config.permits(user['user_id']) and analytics.permits(user['user_id'])
    def cost_access(user):
        return settings.app_environment in {'dev','test'} and authorized(user) and UUID(str(user['user_id'])) in config.cost_report_user_ids
    def authorize(user,request):
        if not authorized(user):
            store.audit(user['user_id'],'query.denied','questions',request.state.request_id,'denied')
            raise HTTPException(403)
    @api.get('/config')
    def options(request:Request,user=Depends(current_user)):
        store.audit(user['user_id'],'query.config','questions',request.state.request_id)
        provider_access=analytics.permits(user['user_id'],True)
        return {'enabled':authorized(user),'provider_access':provider_access,'synthetic_data':config.synthetic_data,
            'demo_questions':list(DEMO_QUESTIONS) if config.transport=='demo' else [],
            'transport':config.transport,'provider_name':config.provider_name,'model':config.model,'requests_per_window':config.requests_per_window,
            'window_seconds':config.window_seconds,'cache_seconds':config.cache_seconds,
            'cost_report_access':cost_access(user),
            'diagnostics_enabled':settings.app_environment in {'dev','test'},
            'supported_questions':[q.description for q in allowed_catalog(provider_access)],
            'disclosure':('Local Ollama: questions, query context and aggregate results are sent to the configured local model. Only synthetic dev/test data is permitted. Questions and usage are retained in clinic query logs. No external LLM API is used; local compute costs are not included. Do not enter patient identifiers.' if config.transport=='ollama' else 'Local deterministic demo: no question or result is sent to an external API. Only the listed fixed demo questions are recognized. This does not validate real LLM translation quality.' if config.transport=='demo' else 'Your question, reviewed query context and returned aggregate financial values are sent to the configured third-party LLM provider. Provider identifiers and recorded costs are also sent when your account has provider access and the selected query requires them. Questions and usage are retained in clinic query logs. Do not enter patient identifiers.')}
    @api.post('')
    def ask(body:Question,request:Request,user=Depends(current_user)):
        authorize(user,request)
        if not body.question.strip(): raise HTTPException(422)
        try: check_range(body.start,body.end)
        except ValueError: raise HTTPException(422) from None
        provider_access=body.allow_provider_data and analytics.permits(user['user_id'],True)
        if body.allow_provider_data and not provider_access:
            store.audit(user['user_id'],'query.denied','provider-questions',request.state.request_id,'denied')
            raise HTTPException(403)
        status,result=service.ask(body,user['user_id'],request.state.request_id,provider_access)
        if settings.app_environment not in {'dev','test'}:
            result={k:v for k,v in result.items() if k not in {'sql','parameters'}}
        return JSONResponse(status_code=status,content=json_exact(result))
    @api.get('/costs')
    def costs(request:Request,start:date,end:date,user=Depends(current_user)):
        authorize(user,request)
        if not cost_access(user):
            store.audit(user['user_id'],'query.denied','query-costs',request.state.request_id,'denied')
            raise HTTPException(403)
        try: check_range(start,end)
        except ValueError: raise HTTPException(422) from None
        return JSONResponse(content=json_exact({'rows':repo.costs(user['user_id'],request.state.request_id,start,end),
            'note':'Cost is an estimate from configured token prices, not a provider invoice. Unknown usage and incomplete requests mean the estimate is partial.'}))
    from .chat_routes import router as chat_router
    from ..simulation.config import load_config as load_simulation
    api.include_router(chat_router(settings,current_user,store,service,analytics,simulation_config or load_simulation(settings.simulation_config_path),conversation_repo,budget_repo,analytics_repo))
    return api
