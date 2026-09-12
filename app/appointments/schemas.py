"""Strict, identifier-free normalized appointment import schemas."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .config import AppointmentConfig


def _validate_amount(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if not value.is_finite() or abs(value) >= Decimal("10000000000000000"):
        raise ValueError("amount must be finite and within the supported range")
    if value.as_tuple().exponent < -2:
        raise ValueError("amount must have at most two decimal places")
    return value


class AppointmentRowInput(BaseModel):
    """One aggregate row; no person-level fields are accepted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: date
    clinic_location: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    appointment_count: StrictInt = Field(ge=0, le=2147483647)
    billed_amount: Decimal | None = None
    collected_amount: Decimal | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_only_canonical_category_name(cls, value: Any) -> Any:
        # ``category_key`` is a harmless compatibility spelling for a
        # normalized caller.  It is converted before extra-field validation;
        # arbitrary source columns still fail closed.
        if isinstance(value, dict) and "category" not in value and "category_key" in value:
            value = dict(value)
            value["category"] = value.pop("category_key")
        return value

    @field_validator("appointment_count", mode="before")
    @classmethod
    def reject_boolean_count(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("appointment_count must be an integer")
        return value

    @field_validator("billed_amount", "collected_amount", mode="before")
    @classmethod
    def reject_binary_currency_inputs(cls, value: Any) -> Any:
        # JSON numbers may already be IEEE-754 floats by the time they reach
        # this boundary.  Require decimal text for HTTP payloads while still
        # allowing Decimal values for trusted internal callers and tests.
        if value is None or isinstance(value, (str, Decimal)):
            return value
        raise ValueError("amount must be a decimal string or null")

    @field_validator("clinic_location")
    @classmethod
    def validate_clinic(cls, value: str) -> str:
        if value == "Unassigned":
            raise ValueError("An approved clinic location is required")
        return value

    _billed = field_validator("billed_amount")(_validate_amount)
    _collected = field_validator("collected_amount")(_validate_amount)


class AppointmentImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AppointmentRowInput] = Field(min_length=1, max_length=5000)
    source_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    # A replacement is explicit and is never inferred from overlapping dates.
    replace_upload_id: UUID | None = None


def normalize_rows(request: AppointmentImportRequest, config: AppointmentConfig) -> tuple[list[dict[str, object]], str]:
    """Validate approved categories/clinics and return safe worker payload."""

    # Source labels are accepted only when an administrator has supplied an
    # explicit mapping.  Canonical keys continue to work directly.  The
    # normalized payload never retains the source label.
    canonical_categories = {
        row.category: config.category_mappings.get(row.category, row.category)
        for row in request.rows
    }
    unknown_categories = sorted(
        {
            canonical
            for canonical in canonical_categories.values()
            if canonical not in config.categories
        }
    )
    if unknown_categories:
        raise ValueError("Each appointment row must use an approved appointment category or mapped source label")
    if not config.clinic_locations:
        raise ValueError("Appointment imports require an approved clinic location list")
    unknown_clinics = sorted(
        {row.clinic_location for row in request.rows if row.clinic_location not in config.clinic_locations}
    )
    if unknown_clinics:
        raise ValueError("Each appointment row must use an approved clinic location")
    rows: list[dict[str, object]] = []
    for source_row, row in enumerate(request.rows, start=1):
        rows.append({
            "source_row": source_row,
            "date": row.date.isoformat(),
            "clinic_location": row.clinic_location,
            "category": canonical_categories[row.category],
            "appointment_count": row.appointment_count,
            # Fixed two-place serialization makes 1, 1.0 and 1.00 the same
            # normalized import identity while preserving unknown as null.
            "billed_amount": None if row.billed_amount is None else format(row.billed_amount, ".2f"),
            "collected_amount": None if row.collected_amount is None else format(row.collected_amount, ".2f"),
        })
    canonical_digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    # ``source_hash`` may identify the original export, but it is never the
    # idempotency key.  The route/repository persist the canonical digest.
    return rows, canonical_digest


class AppointmentSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    upload_id: UUID
    content_hash: str
    source_hash: str | None = None
    status: str
    total_rows: int
    rows_accepted: int
    rows_rejected: int
