"""Authenticated appointment activity API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..analytics.config import load_config as load_analytics_config
from ..analytics.calculations import check_range
from ..ingestion.config import load_config as load_ingestion_config
from .aggregation import aggregate_report, matched_prior_range
from .config import AppointmentConfig, resolve_config
from .repository import AppointmentRepository, AppointmentUploadConflict
from .schemas import AppointmentImportRequest, normalize_rows


def json_exact(value):
    """Serialize Decimal and date values without binary float conversion."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_exact(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_exact(item) for item in value]
    return value


def router(
    settings,
    current_user,
    store,
    config=None,
    repo=None,
    analytics_config=None,
    ingestion_config=None,
):
    """Build the appointment router with existing app auth/config objects."""

    standalone_config = config is not None and analytics_config is None and ingestion_config is None
    if analytics_config is None and not standalone_config:
        analytics_config = load_analytics_config(getattr(settings, "analytics_config_path", None))
    if ingestion_config is None and not standalone_config:
        ingestion_config = load_ingestion_config(getattr(settings, "ingestion_config_path", None))
    appointment_config = resolve_config(
        config,
        analytics_config=analytics_config,
        ingestion_config=ingestion_config,
    )
    repo = repo or AppointmentRepository(settings, appointment_config)
    api = APIRouter(prefix="/api/v1/appointments")

    def read_permitted(user) -> bool:
        if analytics_config is not None and hasattr(analytics_config, "permits"):
            return bool(analytics_config.permits(user["user_id"]))
        return appointment_config.permits_read(user["user_id"])

    def write_permitted(user) -> bool:
        if ingestion_config is not None and hasattr(ingestion_config, "permits"):
            return bool(ingestion_config.permits(user["user_id"]))
        return appointment_config.permits_write(user["user_id"])

    def read_authorized(request: Request, user=Depends(current_user)):
        if not read_permitted(user):
            store.audit(user["user_id"], "appointment.denied", "appointment-activity", request.state.request_id, "denied")
            raise HTTPException(403)
        return user

    def write_authorized(request: Request, user=Depends(current_user)):
        if not write_permitted(user):
            store.audit(user["user_id"], "appointment.denied", "appointment-import", request.state.request_id, "denied")
            raise HTTPException(403)
        return user

    def check_filters(clinic_location: str | None, category: str | None) -> None:
        if clinic_location and appointment_config.clinic_locations and clinic_location not in appointment_config.clinic_locations:
            raise HTTPException(422, detail="Select an approved clinic location")
        if category and category not in appointment_config.categories:
            raise HTTPException(422, detail="Select an approved appointment category")

    def complete_date_coverage(rows, start: date, end: date) -> bool:
        # Aggregate exports must include an explicit row (including count=0)
        # for every date before a matched-period change is presented as exact.
        from .aggregation import _date_coverage_complete

        return _date_coverage_complete(rows, start, end)

    @api.get("/config")
    def options(request: Request, user=Depends(current_user)):
        can_read = read_permitted(user)
        can_import = write_permitted(user)
        store.audit(user["user_id"], "appointment.config", "appointment-activity", request.state.request_id)
        return {
            "enabled": can_read,
            "read_enabled": can_read,
            "can_import": can_import,
            "categories": appointment_config.categories if can_read or can_import else {},
            "category_labels": appointment_config.categories if can_read or can_import else {},
            "category_mappings": appointment_config.category_mappings if can_import else {},
            "clinic_locations": appointment_config.clinic_locations if can_read or can_import else [],
            "measure": "appointment_volume",
            "measure_label": "Appointments (aggregate volume)",
            "unique_patient_measure_available": False,
            "max_rows": 5000,
            "currency": appointment_config.currency,
        }

    @api.get("/metadata")
    def metadata(request: Request, user=Depends(read_authorized)):
        result = repo.metadata(user["user_id"], request.state.request_id)
        result = dict(result or {})
        # Configured clinics/categories remain visible even before their first
        # aggregate row, while observed metadata is still safe and additive.
        result["clinic_locations"] = appointment_config.clinic_locations or result.get("clinic_locations", [])
        result["categories"] = list(appointment_config.categories)
        return JSONResponse(content=json_exact(result))

    @api.get("/locations")
    def locations(request: Request, user=Depends(read_authorized)):
        store.audit(user["user_id"], "appointment.locations", "appointment-activity", request.state.request_id)
        observed = {}
        try:
            observed = dict(repo.metadata(user["user_id"], request.state.request_id) or {})
        except AttributeError:
            observed = {}
        return {"clinic_locations": appointment_config.clinic_locations or observed.get("clinic_locations", [])}

    @api.get("/report")
    def report(
        request: Request,
        start: date,
        end: date,
        frequency: Literal["week", "month", "quarter"] = "week",
        clinic_location: str | None = None,
        category: str | None = None,
        user=Depends(read_authorized),
    ):
        try:
            check_range(start, end)
        except ValueError:
            raise HTTPException(422, detail="Select an inclusive date range of at most ten years between 1900 and 2199") from None
        check_filters(clinic_location, category)
        try:
            prior_start, prior_end = matched_prior_range(start, end, frequency)
            # The comparison range is also bounded.  This rejects valid
            # current ranges whose matched prior period would underflow the
            # supported date boundary (for example, January 1900).
            check_range(prior_start, prior_end)
            current = repo.rows(
                user["user_id"], request.state.request_id, start, end,
                clinic_location=clinic_location, category=category,
            )
            prior = repo.rows(
                user["user_id"], request.state.request_id, prior_start, prior_end,
                clinic_location=clinic_location, category=category,
            )
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from None
        prior_complete = complete_date_coverage(prior, prior_start, prior_end)
        current_complete = complete_date_coverage(current, start, end)
        result = aggregate_report(
            current,
            start,
            end,
            frequency,
            labels=appointment_config.categories,
            prior_rows=prior,
            prior_range=(prior_start, prior_end),
            prior_complete=prior_complete,
            current_complete=current_complete,
        )
        result["currency"] = appointment_config.currency
        return JSONResponse(content=json_exact(result))

    @api.post("/imports")
    async def enqueue_import(body: AppointmentImportRequest, request: Request, user=Depends(write_authorized)):
        try:
            rows, digest = normalize_rows(body, appointment_config)
            result, duplicate = await run_in_threadpool(
                repo.enqueue,
                user["user_id"], digest, rows, request.state.request_id,
                appointment_config.digest(), body.replace_upload_id, body.source_hash,
            )
        except AppointmentUploadConflict:
            raise HTTPException(409) from None
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from None
        return JSONResponse(status_code=200 if duplicate else 202, content=jsonable_encoder({**result, "duplicate": duplicate}))

    @api.get("/imports/{upload_id}")
    def import_summary(upload_id: UUID, request: Request, user=Depends(write_authorized)):
        result = repo.summary(upload_id, user["user_id"], request.state.request_id)
        if result is None:
            raise HTTPException(404)
        return JSONResponse(content=jsonable_encoder(result))

    @api.post("/imports/{upload_id}/retry")
    def retry_import(upload_id: UUID, request: Request, user=Depends(write_authorized)):
        try:
            result = repo.retry(upload_id, user["user_id"], request.state.request_id)
        except AppointmentUploadConflict:
            raise HTTPException(409) from None
        if result is None:
            raise HTTPException(404)
        return JSONResponse(status_code=202, content=jsonable_encoder(result))

    @api.delete("/imports/{upload_id}")
    def delete_import(upload_id: UUID, request: Request, user=Depends(write_authorized)):
        result = repo.soft_delete(upload_id, user["user_id"], request.state.request_id)
        if result is None:
            raise HTTPException(404)
        return JSONResponse(content=jsonable_encoder(result))

    return api
