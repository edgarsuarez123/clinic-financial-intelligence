from uuid import UUID
import psycopg
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from fastapi.responses import JSONResponse
from .chat_repository import ConversationRepository
from .chat_service import ChatService
from .chat_schemas import ConversationCreate,Turn,Rename,Revision
from ..analytics.routes import json_exact
from ..simulation.repository import BudgetRepository,BudgetMissing,BudgetConflict
from ..analytics.repository import AnalyticsRepository

def public_document(value,diagnostics=False):
    if isinstance(value,list): return [public_document(v,diagnostics) for v in value]
    if not isinstance(value,dict): return value
    private={'owner_id','input_hash','attempt_id','requires_provider_access','requires_simulation_access'}
    if not diagnostics: private|={'sql','parameters','data_revision'}
    return {k:public_document(v,diagnostics) for k,v in value.items() if k not in private}

def router(settings,current_user,store,query_service,analytics,simulation,conversations=None,budgets=None,analytics_repo=None):
    conversations=conversations or ConversationRepository(settings)
    service=ChatService(query_service,budgets or BudgetRepository(settings),analytics_repo or AnalyticsRepository(settings))
    api=APIRouter(prefix='/conversations')
    diagnostics=settings.app_environment in {'dev','test'}
    def permissions(user,request):
        uid=user['user_id']
        if not query_service.config.permits(uid) or not analytics.permits(uid):
            store.audit(uid,'conversation.denied','conversations',request.state.request_id,'denied')
            raise HTTPException(403)
        return analytics.permits(uid,True),simulation.permits(uid)
    def response(value): return JSONResponse(content=json_exact(public_document(value,diagnostics)))
    def failure(exc,request,user):
        store.audit(user['user_id'],'conversation.denied' if isinstance(exc,BudgetMissing) else 'conversation.conflict','conversations',request.state.request_id,'denied')
        if isinstance(exc,BudgetMissing): raise HTTPException(404)
        return JSONResponse(status_code=409,content={'error':{'code':'conversation_conflict','message':'This conversation changed or a reply is still running. Reopen it before sending again. Interrupted replies can be retried after six minutes.','request_id':request.state.request_id}})
    @api.get('')
    def list_chats(request:Request,offset:int=Query(0,ge=0,le=100000),user=Depends(current_user)):
        p,s=permissions(user,request)
        return response(conversations.list(user['user_id'],request.state.request_id,p,s,offset))
    @api.post('')
    def create(body:ConversationCreate,request:Request,user=Depends(current_user)):
        permissions(user,request)
        try: return response(conversations.create(body,user['user_id'],request.state.request_id))
        except (BudgetMissing,BudgetConflict) as exc: return failure(exc,request,user)
    @api.get('/{key}')
    def read(key:UUID,request:Request,user=Depends(current_user)):
        p,s=permissions(user,request)
        try: return response(conversations.get(key,user['user_id'],request.state.request_id,p,s))
        except (BudgetMissing,BudgetConflict) as exc: return failure(exc,request,user)
    @api.patch('/{key}')
    def rename(key:UUID,body:Rename,request:Request,user=Depends(current_user)):
        p,s=permissions(user,request)
        try: return response(conversations.change(key,user['user_id'],request.state.request_id,p,s,body.expected_revision,title=body.title))
        except (BudgetMissing,BudgetConflict) as exc: return failure(exc,request,user)
    @api.delete('/{key}')
    def delete(key:UUID,body:Revision,request:Request,user=Depends(current_user)):
        p,s=permissions(user,request)
        try:
            conversations.change(key,user['user_id'],request.state.request_id,p,s,body.expected_revision,delete=True)
            return response({'deleted':True})
        except (BudgetMissing,BudgetConflict) as exc: return failure(exc,request,user)
    @api.post('/{key}/turns')
    def ask(key:UUID,body:Turn,request:Request,user=Depends(current_user)):
        p,s=permissions(user,request);uid=user['user_id'];rid=request.state.request_id
        try:
            old=conversations.get(key,uid,rid,p,s)
            previous,attempt=conversations.begin(key,body,uid,rid,p,s)
            if previous is not None: return response(conversations.get(key,uid,rid,p,s))
            try:
                result=service.ask(body,old['turns'],uid,rid,p,s,lambda a,b:conversations.protect(key,uid,rid,a,b))
            except psycopg.Error:
                result={'status':'unavailable','answer':'A financial service is unavailable. Your question has been saved.'}
            conversations.finish(key,body.turn_id,attempt,uid,rid,result,result.get('requires_provider_access',False),result.get('requires_simulation_access',False))
            return response(conversations.get(key,uid,rid,p,s))
        except (BudgetMissing,BudgetConflict) as exc: return failure(exc,request,user)
        except ValueError:
            return JSONResponse(status_code=422,content={'error':{'code':'invalid_conversation','message':'Start a new conversation or check the selected context.','request_id':rid}})
    return api
