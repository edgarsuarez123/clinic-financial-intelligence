from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.appointments.aggregation import AppointmentFact
from app.appointments.config import AppointmentConfig, resolve_config
from app.main import create_app
from app.settings import Settings
from test_api import MemoryStore, login


class AppointmentMemoryRepository:
    """Small repository double for HTTP validation and serialization tests."""

    def __init__(self):
        self.imports = {}
        self.enqueue_calls = []
        self.read_calls = []

    def metadata(self, uid, request_id):
        return {
            "first_date": date(2025, 12, 29),
            "last_date": date(2026, 1, 11),
            "row_count": 14,
            "clinic_locations": ["North"],
            "categories": ["new_patient"],
        }

    def rows(self, uid, request_id, start, end, *, clinic_location=None, category=None):
        self.read_calls.append((start, end, clinic_location, category))
        rows = []
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            rows.append(
                AppointmentFact(
                    activity_date=day,
                    clinic_location="North",
                    category="new_patient",
                    appointment_count=1,
                    billed_amount=Decimal("10.00"),
                    collected_amount=Decimal("8.00"),
                )
            )
        return rows

    def enqueue(self, uid, content_hash, rows, request_id, mapping_hash=None, replace_upload_id=None, source_hash=None):
        self.enqueue_calls.append(
            {
                "uid": uid,
                "content_hash": content_hash,
                "rows": rows,
                "mapping_hash": mapping_hash,
                "replace_upload_id": replace_upload_id,
                "source_hash": source_hash,
            }
        )
        duplicate = content_hash in self.imports
        if duplicate:
            return self.imports[content_hash], True
        upload_id = uuid4()
        result = {
            "upload_id": upload_id,
            "content_hash": content_hash,
            "source_hash": source_hash,
            "replaces_upload_id": replace_upload_id,
            "status": "pending",
            "total_rows": len(rows),
            "rows_accepted": 0,
            "rows_rejected": 0,
            "rejections": [],
            "failure_code": None,
            "created_at": None,
            "updated_at": None,
            "deleted_at": None,
        }
        self.imports[content_hash] = result
        return result, False

    def summary(self, upload_id, uid, request_id):
        return next((row for row in self.imports.values() if row["upload_id"] == upload_id), None)

    def retry(self, upload_id, uid, request_id):
        return None

    def soft_delete(self, upload_id, uid, request_id):
        return None


@pytest.fixture
def api():
    store = MemoryStore()
    config = AppointmentConfig(
        authorized_user_ids=[store.user["user_id"]],
        ingestion_authorized_user_ids=[store.user["user_id"]],
        clinic_locations=["North"],
        currency="EUR",
    )
    repo = AppointmentMemoryRepository()
    with TestClient(
        create_app(
            Settings("postgresql://unused"),
            store,
            appointment_config=config,
            appointment_repo=repo,
        )
    ) as client:
        yield client, store, repo


def test_config_and_report_expose_configured_currency(api):
    client, _, repo = api
    _, headers = login(client)

    config = client.get("/api/v1/appointments/config", headers=headers)
    assert config.status_code == 200
    assert config.json()["currency"] == "EUR"

    report = client.get(
        "/api/v1/appointments/report?start=2026-01-05&end=2026-01-11&frequency=week",
        headers=headers,
    )
    assert report.status_code == 200
    body = report.json()
    assert body["currency"] == "EUR"
    assert body["summary"]["appointment_count"] == 7
    assert body["summary"]["billed_amount"] == "70.00"
    assert len(repo.read_calls) == 2


def test_resolve_config_uses_single_currency_from_ingestion_profiles():
    class Profile:
        currency = "GBP"

    class Ingestion:
        clinic_locations = ["North"]
        profiles = {"demo": Profile()}

    resolved = resolve_config(ingestion_config=Ingestion())
    assert resolved.currency == "GBP"


@pytest.mark.parametrize(
    "query",
    [
        "start=2026-01-11&end=2026-01-05",
        "start=1899-12-31&end=1900-01-01",
        "start=1900-01-01&end=1900-01-01",
        "start=2026-01-01&end=2036-02-01",
    ],
)
def test_report_rejects_invalid_or_unsupported_ranges_without_reading(api, query):
    client, _, repo = api
    _, headers = login(client)
    response = client.get(f"/api/v1/appointments/report?{query}", headers=headers)
    assert response.status_code == 422
    assert repo.read_calls == []


@pytest.mark.parametrize(
    "row",
    [
        {
            "date": "2026-01-05",
            "clinic_location": "North",
            "category": "unknown",
            "appointment_count": 1,
        },
        {
            "date": "2026-01-05",
            "clinic_location": "Unconfigured",
            "category": "new_patient",
            "appointment_count": 1,
        },
        {
            "date": "2026-01-05",
            "clinic_location": "North",
            "category": "new_patient",
            "appointment_count": True,
        },
        {
            "date": "2026-01-05",
            "clinic_location": "North",
            "category": "new_patient",
            "appointment_count": 1,
            "patient_id": "person-should-never-be-accepted",
        },
        {
            "date": "2026-01-05",
            "clinic_location": "North",
            "category": "new_patient",
            "appointment_count": 1,
            "billed_amount": 1.25,
        },
    ],
)
def test_import_rejects_unapproved_or_identifier_fields(api, row):
    client, _, repo = api
    _, headers = login(client)
    response = client.post("/api/v1/appointments/imports", json={"rows": [row]}, headers=headers)
    assert response.status_code == 422
    assert "person-should-never-be-accepted" not in response.text
    assert repo.enqueue_calls == []


def test_canonical_rows_are_idempotent_even_when_source_hash_changes(api):
    client, _, repo = api
    _, headers = login(client)
    row = {
        "date": "2026-01-05",
        "clinic_location": "North",
        "category": "new_patient",
        "appointment_count": 2,
        "billed_amount": "20.00",
    }
    first = client.post(
        "/api/v1/appointments/imports",
        json={"rows": [row], "source_hash": "a" * 64},
        headers=headers,
    )
    second = client.post(
        "/api/v1/appointments/imports",
        json={"rows": [row], "source_hash": "b" * 64},
        headers=headers,
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["upload_id"] == first.json()["upload_id"]
    assert len(repo.enqueue_calls) == 2
    assert set(repo.enqueue_calls[0]["rows"][0]) == {
        "source_row",
        "date",
        "clinic_location",
        "category",
        "appointment_count",
        "billed_amount",
        "collected_amount",
    }
    assert all("patient_id" not in call["rows"][0] for call in repo.enqueue_calls)


def test_read_permission_is_separate_from_import_permission():
    store = MemoryStore()
    config = AppointmentConfig(
        authorized_user_ids=[],
        ingestion_authorized_user_ids=[store.user["user_id"]],
        clinic_locations=["North"],
    )
    repo = AppointmentMemoryRepository()
    with TestClient(
        create_app(Settings("postgresql://unused"), store, appointment_config=config, appointment_repo=repo)
    ) as client:
        _, headers = login(client)
        assert client.get("/api/v1/appointments/report?start=2026-01-05&end=2026-01-05", headers=headers).status_code == 403
        response = client.post(
            "/api/v1/appointments/imports",
            json={
                "rows": [
                    {
                        "date": "2026-01-05",
                        "clinic_location": "North",
                        "category": "new_patient",
                        "appointment_count": 1,
                    }
                ]
            },
            headers=headers,
        )
        assert response.status_code == 202
