"""Configuration and access policy for appointment activity.

Appointments intentionally reuse the existing analytics (read) and
ingestion (write) allow lists.  This module has a small standalone config
model so tests and deployments can provide those existing config objects
without adding another permission system.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_CATEGORY_LABELS: dict[str, str] = {
    "new_patient": "New patient",
    "radiology": "Radiology",
    "lab": "Lab",
    "follow_up": "Follow-up",
    "preventive": "Preventive",
    "other": "Other",
}
_CATEGORY_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class AppointmentConfig(BaseModel):
    """Approved canonical labels and the optional standalone access lists.

    In the integrated app, ``analytics_config`` and ``ingestion_config`` are
    passed to :func:`app.appointments.routes.router` and their ``permits``
    methods are authoritative.  The access lists here are useful for a
    focused test or a deployment that supplies a single appointment config.

    ``categories`` is canonical key -> display label.  ``category_mappings``
    is source label -> canonical key and is only used during an explicit
    source projection; no source label is persisted in an activity fact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorized_user_ids: list[UUID] = Field(default_factory=list)
    ingestion_authorized_user_ids: list[UUID] = Field(default_factory=list)
    categories: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_CATEGORY_LABELS))
    category_mappings: dict[str, str] = Field(default_factory=dict)
    clinic_locations: list[str] = Field(default_factory=list, max_length=100)
    # Appointment amounts are kept separate from the financial ledger, but
    # still need an explicit display currency.  Existing deployments already
    # configure one currency for their ingestion profiles; USD remains the
    # compatibility default for a standalone appointment configuration.
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("At least one approved appointment category is required")
        for key, label in value.items():
            if not _CATEGORY_KEY.fullmatch(key):
                raise ValueError("Appointment categories must be lower snake case keys")
            if not isinstance(label, str) or not label.strip() or len(label) > 100:
                raise ValueError("Appointment category labels must contain 1–100 characters")
        return dict(value)

    @field_validator("category_mappings")
    @classmethod
    def validate_mappings(cls, value: dict[str, str]) -> dict[str, str]:
        for source, canonical in value.items():
            if not isinstance(source, str) or not source.strip() or len(source) > 100:
                raise ValueError("Appointment source labels must contain 1–100 characters")
            if not _CATEGORY_KEY.fullmatch(canonical):
                raise ValueError("Appointment mappings must target a canonical category")
        return dict(value)

    @field_validator("clinic_locations")
    @classmethod
    def validate_clinics(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(
            not isinstance(item, str)
            or not item.strip()
            or item != item.strip()
            or len(item) > 100
            or item == "Unassigned"
            for item in value
        ):
            raise ValueError("Clinic locations must be unique, nonempty names; Unassigned is reserved")
        return list(value)

    @model_validator(mode="after")
    def validate_mapping_targets(self) -> "AppointmentConfig":
        unknown = set(self.category_mappings.values()) - set(self.categories)
        if unknown:
            raise ValueError("Appointment mappings must target configured categories")
        return self

    def permits_read(self, uid: UUID | str) -> bool:
        return UUID(str(uid)) in self.authorized_user_ids

    def permits_write(self, uid: UUID | str) -> bool:
        return UUID(str(uid)) in self.ingestion_authorized_user_ids

    def category_label(self, key: str) -> str:
        return self.categories.get(key, key)

    def digest(self) -> str:
        payload = {
            "categories": self.categories,
            "category_mappings": self.category_mappings,
            "clinic_locations": self.clinic_locations,
            "currency": self.currency,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _mapping_from_ingestion(ingestion: Any) -> dict[str, str]:
    """Read either spelling used by early integration branches.

    The canonical field for the integrated ingestion config is
    ``appointment_category_mappings``.  Accepting the short aliases keeps a
    deployed config forward compatible while still requiring an explicit
    mapping.
    """

    for name in ("appointment_category_mappings", "appointment_mappings", "category_mappings"):
        value = getattr(ingestion, name, None)
        if isinstance(value, Mapping):
            return {str(k): str(v) for k, v in value.items()}
    return {}


def _labels_from_ingestion(ingestion: Any) -> dict[str, str]:
    for name in ("appointment_category_labels", "appointment_categories"):
        value = getattr(ingestion, name, None)
        if not isinstance(value, Mapping):
            continue
        # Most configs expose canonical -> readable label.  If the value is a
        # nested object, prefer its explicit label/source values.
        labels: dict[str, str] = {}
        for key, item in value.items():
            if isinstance(item, str):
                labels[str(key)] = item
            elif isinstance(item, Mapping) and isinstance(item.get("label"), str):
                labels[str(key)] = str(item["label"])
        if labels:
            return labels
    return {}


def resolve_config(
    config: AppointmentConfig | Any | None = None,
    *,
    analytics_config: Any | None = None,
    ingestion_config: Any | None = None,
) -> AppointmentConfig:
    """Build an appointment config from existing app configuration objects."""

    if isinstance(config, AppointmentConfig):
        return config

    raw = config.model_dump() if isinstance(config, BaseModel) else dict(config or {})
    labels = dict(DEFAULT_CATEGORY_LABELS)
    labels.update({str(k): str(v) for k, v in raw.get("categories", {}).items()})
    labels.update(_labels_from_ingestion(ingestion_config))
    mappings = dict(raw.get("category_mappings", {}))
    mappings.update(_mapping_from_ingestion(ingestion_config))
    read_ids = list(raw.get("authorized_user_ids", []))
    write_ids = list(raw.get("ingestion_authorized_user_ids", []))
    clinics = list(raw.get("clinic_locations", []))
    currency = str(raw.get("currency", "USD"))
    if ingestion_config is not None:
        clinics = list(getattr(ingestion_config, "clinic_locations", clinics) or clinics)
        currencies = {
            str(profile.currency)
            for profile in (getattr(ingestion_config, "profiles", {}) or {}).values()
            if getattr(profile, "currency", None)
        }
        configured_currency = getattr(ingestion_config, "currency", None)
        if configured_currency:
            currencies.add(str(configured_currency))
        if len(currencies) == 1:
            currency = next(iter(currencies))
    if analytics_config is not None and getattr(analytics_config, "currency", None):
        currency = str(analytics_config.currency)
    return AppointmentConfig(
        authorized_user_ids=read_ids,
        ingestion_authorized_user_ids=write_ids,
        categories=labels,
        category_mappings=mappings,
        clinic_locations=clinics,
        currency=currency,
    )


def load_config(path: str | None) -> AppointmentConfig:
    """Load a standalone JSON appointment config when one is provided."""

    if not path:
        return AppointmentConfig()
    return AppointmentConfig.model_validate_json(Path(path).read_text())
