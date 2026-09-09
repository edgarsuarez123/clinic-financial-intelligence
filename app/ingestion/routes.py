import asyncio
import hashlib
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .config import load_config
from .parsers import FormatError, MAX_BYTES
from .validation import prepare
from .repository import IngestionRepository, UploadConflict


def router(settings, current_user, store, config=None, repo=None):
    config=config or load_config(settings.ingestion_config_path)
    repo=repo or IngestionRepository(settings)
    api=APIRouter(prefix="/api/v1")
    slots=asyncio.Semaphore(2)

    def allowed(request: Request,user=Depends(current_user)):
        if not config.permits(user["user_id"]):
            store.audit(user["user_id"],"upload.denied","ingestion",request.state.request_id,"denied")
            raise HTTPException(403)
        return user

    @api.get("/ingestion/config")
    def options(request: Request,user=Depends(current_user)):
        permitted=config.permits(user["user_id"])
        store.audit(user["user_id"],"ingestion.config","ingestion",request.state.request_id)
        return {"enabled":permitted,"mode":config.mode,"profiles":list(config.profiles) if permitted else [],
                "max_bytes":MAX_BYTES,"formats":["csv","xlsx","pdf"]}

    @api.post("/uploads/{kind}")
    async def upload(kind: str,request: Request,profile: str,user=Depends(allowed)):
        if kind not in {"csv","xlsx","pdf"} or profile not in config.profiles: raise HTTPException(422)
        # Raw request body avoids multipart temporary files. The caller's filename
        # is deliberately neither required nor persisted.
        async with slots:
            data=bytearray()
            async for chunk in request.stream():
                if len(data)+len(chunk)>MAX_BYTES: raise HTTPException(413)
                data.extend(chunk)
            digest=hashlib.sha256(data).hexdigest()
            try:
                prepared=await run_in_threadpool(prepare,bytes(data),kind,config.profiles[profile])
            except FormatError as exc:
                await run_in_threadpool(store.audit,user["user_id"],"upload.rejected","ingestion",request.state.request_id,"denied")
                return JSONResponse(status_code=422,content={"error":{"code":exc.code,"message":str(exc),
                                    "request_id":request.state.request_id}})
            finally:
                data.clear()
            try:
                result,duplicate=await run_in_threadpool(repo.enqueue,user["user_id"],digest,kind,profile,
                                                         config.profiles[profile],prepared,request.state.request_id)
            except UploadConflict:
                await run_in_threadpool(store.audit,user["user_id"],"upload.conflict","ingestion",request.state.request_id,"denied")
                raise HTTPException(409) from None
        return JSONResponse(status_code=200 if duplicate else 202,content=jsonable_encoder({**result,"duplicate":duplicate}))

    @api.get("/uploads/{upload_id}")
    def summary(upload_id: UUID,request: Request,user=Depends(allowed)):
        result=repo.summary(upload_id,user["user_id"],request.state.request_id)
        if result is None: raise HTTPException(404)
        return result

    @api.post("/uploads/{upload_id}/retry")
    def retry(upload_id: UUID,request: Request,user=Depends(allowed)):
        try: result=repo.retry(upload_id,user["user_id"],request.state.request_id)
        except UploadConflict: raise HTTPException(409) from None
        if result is None: raise HTTPException(404)
        return JSONResponse(status_code=202,content=jsonable_encoder(result))

    return api
