from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import logging
import secrets
import time
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_config import configure
from .security import DUMMY_HASH, verify_password, token_hash
from .settings import Settings
from .store import Store

class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.@+-]+$")
    password: str = Field(min_length=1, max_length=256)

class TokenOutput(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime

class UserOutput(BaseModel):
    user_id: str
    username: str

bearer = HTTPBearer(auto_error=False)

def create_app(settings=None, store=None, ingestion_config=None, ingestion_repo=None, analytics_config=None, analytics_repo=None, simulation_config=None, budget_repo=None, query_config=None, query_repo=None, query_executor=None, query_provider=None, conversation_repo=None, appointment_config=None, appointment_repo=None):
    settings = settings or Settings.from_env()
    store = store or Store(settings)
    configure(settings.log_level)
    logger = logging.getLogger("clinic.application")

    @asynccontextmanager
    async def lifespan(app):
        store.check_runtime()
        yield

    app = FastAPI(title="Clinic Financial Intelligence", version="0.6.0",
                  docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def error(request, status, code, message, headers=None):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "request_id": request.state.request_id}}, headers=headers)

    @app.middleware("http")
    async def request_log(request, call_next):
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("", extra={"event":"request.failed", "request_id":request.state.request_id,
                                   "error_type":type(exc).__name__})
            response = error(request, 500, "internal_error", "The request could not be completed.")
        # Only matched route templates are logged; never arbitrary paths or queries.
        route = getattr(request.scope.get("route"), "path", "unmatched")
        logger.info("", extra={"event":"request.completed", "request_id":request.state.request_id,
                    "method":request.method, "route":route, "status":response.status_code,
                    "duration_ms":round((time.monotonic()-start)*1000)})
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        messages = {403:"Access to this feature is not configured for this account.",
                    409:"Upload conflicts with existing content or cannot be retried in this state.",
                    413:"File exceeds the 10 MiB limit.", 401:"Authentication required or credentials invalid.", 404:"Resource not found.",
                    405:"Method not allowed.", 429:"Too many login attempts. Try again later."}
        return error(request, exc.status_code, f"http_{exc.status_code}",
                     messages.get(exc.status_code,"Request could not be completed."), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo Pydantic input values (could include passwords or identifiers).
        if request.url.path.startswith('/api/v1/simulations/'):
            from .validation import simulation_issues
            issues=simulation_issues(exc.errors())
            message='Check the highlighted plan inputs.'
            if issues: message=f"{issues[0]['field']}: {issues[0]['message']}"
            return JSONResponse(status_code=422,content={'error':{'code':'invalid_request','message':message,
                'issues':issues,'request_id':request.state.request_id}})
        return error(request,422,"invalid_request","Request fields are missing or invalid.")

    def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        user = None
        if credentials and len(credentials.credentials) <= 256:
            user = store.resolve_session(token_hash(credentials.credentials))
        if not user:
            store.audit(None,"auth.denied","api",request.state.request_id,"denied")
            raise HTTPException(401,headers={"WWW-Authenticate":"Bearer"})
        request.state.digest = token_hash(credentials.credentials)
        return user

    @app.post("/api/v1/auth/login", response_model=TokenOutput)
    def login(body: LoginInput, request: Request):
        if not store.login_allowed(body.username):
            store.audit(None,"auth.throttled","auth",request.state.request_id,"denied")
            raise HTTPException(429,headers={"Retry-After":str(settings.login_window_seconds)})
        user = store.find_user(body.username)
        valid = verify_password(user["password_hash"] if user else DUMMY_HASH,body.password)
        if not user or not valid:
            store.audit(None,"auth.login","auth",request.state.request_id,"denied")
            raise HTTPException(401,headers={"WWW-Authenticate":"Bearer"})
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc)+timedelta(minutes=settings.session_minutes)
        if not store.create_session(user["user_id"],token_hash(token),expires_at,request.state.request_id):
            raise HTTPException(401)
        return TokenOutput(access_token=token,expires_at=expires_at)

    @app.get("/api/v1/auth/me", response_model=UserOutput)
    def me(request: Request, user=Depends(current_user)):
        store.audit(user["user_id"],"account.read","self",request.state.request_id)
        return UserOutput(user_id=str(user["user_id"]),username=user["username"])

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request, user=Depends(current_user)):
        store.revoke_session(request.state.digest,user["user_id"],request.state.request_id)

    @app.get("/api/v1/health")
    def health(request: Request, user=Depends(current_user)):
        store.ready()
        store.audit(user["user_id"],"health.read","system",request.state.request_id)
        return {"status":"ok","phase":5}

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def schema(request: Request, user=Depends(current_user)):
        store.audit(user["user_id"],"schema.read","system",request.state.request_id)
        return app.openapi()

    from .ingestion.routes import router
    app.include_router(router(settings,current_user,store,ingestion_config,ingestion_repo))
    from .analytics.routes import router as analytics_router
    app.include_router(analytics_router(settings,current_user,store,analytics_config,analytics_repo))
    from .simulation.routes import router as simulation_router
    app.include_router(simulation_router(settings,current_user,store,simulation_config,analytics_config,analytics_repo,budget_repo))
    from .query.routes import router as query_router
    app.include_router(query_router(settings,current_user,store,query_config,analytics_config,query_repo,query_executor,query_provider,simulation_config,budget_repo,analytics_repo,conversation_repo))
    from .appointments.routes import router as appointment_router
    app.include_router(appointment_router(settings,current_user,store,appointment_config,appointment_repo,analytics_config,ingestion_config))
    return app
