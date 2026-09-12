"""PostgreSQL-backed appointment queue, replacement and access tests."""

import hashlib
import json
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.appointments.config import AppointmentConfig
from app.appointments.repository import AppointmentRepository, AppointmentUploadConflict
from app.settings import Settings
from test_postgres import db


pytestmark = pytest.mark.integration


def _rows(day="2026-01-05", count=2, *, category="new_patient", clinic="North"):
    return [
        {
            "source_row": 1,
            "date": day,
            "clinic_location": clinic,
            "category": category,
            "appointment_count": count,
            "billed_amount": "20.00",
            "collected_amount": "15.00",
        }
    ]


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture
def appointment_repo(db):
    uid = uuid4()
    config = AppointmentConfig(
        authorized_user_ids=[uid],
        ingestion_authorized_user_ids=[uid],
        clinic_locations=[f"North-{uid.hex[:8]}"],
    )
    with psycopg.connect(db[0]) as conn:
        conn.execute(
            "INSERT INTO core.app_user (user_id,username,password_hash) VALUES (%s,%s,'synthetic')",
            (uid, str(uid)),
        )
    return AppointmentRepository(Settings(db[1]), config), uid, config


def test_duplicate_normalized_batch_does_not_add_facts(db, appointment_repo):
    repo, uid, config = appointment_repo
    clinic = config.clinic_locations[0]
    rows = _rows(clinic=clinic)
    digest = _digest(rows)
    first, duplicate = repo.enqueue(uid, digest, rows, uuid4(), config.digest(), source_hash="a" * 64)
    assert duplicate is False
    assert repo.process_one() is True

    second, duplicate = repo.enqueue(uid, digest, rows, uuid4(), config.digest(), source_hash="b" * 64)
    assert duplicate is True
    assert second["upload_id"] == first["upload_id"]
    assert repo.process_one() is False

    with psycopg.connect(db[0]) as conn:
        assert conn.execute(
            "SELECT count(*) FROM analytics.appointment_activity WHERE source_upload_id=%s AND deleted_at IS NULL",
            (first["upload_id"],),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT count(*) FROM audit.audit_log WHERE target=%s AND action='appointment.upload.duplicate'",
            (str(first["upload_id"]),),
        ).fetchone()[0] == 1


def test_worker_audit_failure_rolls_back_facts_and_status(db, appointment_repo, monkeypatch):
    repo, uid, config = appointment_repo
    rows = _rows(clinic=config.clinic_locations[0])
    upload, _ = repo.enqueue(uid, _digest(rows), rows, uuid4(), config.digest())

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(repo, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        repo.process_one()

    with psycopg.connect(db[0]) as conn:
        assert conn.execute(
            "SELECT status FROM core.appointment_upload WHERE upload_id=%s", (upload["upload_id"],)
        ).fetchone()[0] == "pending"
        assert conn.execute(
            "SELECT count(*) FROM analytics.appointment_activity WHERE source_upload_id=%s",
            (upload["upload_id"],),
        ).fetchone()[0] == 0
    monkeypatch.undo()
    assert repo.process_one() is True


def test_worker_uses_the_queued_category_snapshot(db, appointment_repo):
    repo, uid, config = appointment_repo
    clinic = config.clinic_locations[0]
    queued_config = AppointmentConfig(
        authorized_user_ids=[uid],
        ingestion_authorized_user_ids=[uid],
        categories={**config.categories, "new_patient": "Initial label"},
        clinic_locations=[clinic],
    )
    repo.config = queued_config
    rows = _rows(clinic=clinic)
    upload, _ = repo.enqueue(uid, _digest(rows), rows, uuid4(), queued_config.digest())
    repo.config = AppointmentConfig(
        authorized_user_ids=[uid],
        ingestion_authorized_user_ids=[uid],
        categories={**config.categories, "new_patient": "Changed label"},
        clinic_locations=[clinic],
    )
    assert repo.process_one() is True

    with psycopg.connect(db[0]) as conn:
        assert conn.execute(
            "SELECT category_label FROM analytics.appointment_activity_facts WHERE source_upload_id=%s",
            (upload["upload_id"],),
        ).fetchone()[0] == "Initial label"


def test_replacement_is_atomic_and_retry_after_completion_is_idempotent(db, appointment_repo):
    repo, uid, config = appointment_repo
    clinic = config.clinic_locations[0]
    original_rows = _rows(count=2, clinic=clinic)
    original, _ = repo.enqueue(uid, _digest(original_rows), original_rows, uuid4(), config.digest())
    assert repo.process_one() is True

    replacement_rows = _rows(day="2026-01-06", count=7, clinic=clinic)
    replacement, duplicate = repo.enqueue(
        uid,
        _digest(replacement_rows),
        replacement_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=original["upload_id"],
    )
    assert duplicate is False
    assert repo.process_one() is True

    # Repeating the exact replacement request after the old source has been
    # retired is a duplicate, not a second replacement conflict.
    retried, duplicate = repo.enqueue(
        uid,
        _digest(replacement_rows),
        replacement_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=original["upload_id"],
    )
    assert duplicate is True
    assert retried["upload_id"] == replacement["upload_id"]

    # A request with the same canonical content but a different replacement
    # relationship is a conflicting upload identity.
    with pytest.raises(AppointmentUploadConflict):
        repo.enqueue(
            uid,
            _digest(replacement_rows),
            replacement_rows,
            uuid4(),
            config.digest(),
            replace_upload_id=uuid4(),
        )

    with psycopg.connect(db[0]) as conn:
        old = conn.execute(
            "SELECT status,deleted_at,replacement_claimed_by FROM core.appointment_upload WHERE upload_id=%s",
            (original["upload_id"],),
        ).fetchone()
        assert old[0] == "completed" and old[1] is not None and old[2] is None
        active = conn.execute(
            "SELECT source_upload_id,appointment_count FROM analytics.appointment_activity_facts WHERE clinic_location=%s ORDER BY source_upload_id",
            (clinic,),
        ).fetchall()
        assert active == [(replacement["upload_id"], 7)]


def test_failed_replacement_retry_reclaims_source_and_soft_delete_releases_claim(db, appointment_repo, monkeypatch):
    repo, uid, config = appointment_repo
    clinic = config.clinic_locations[0]
    original_rows = _rows(count=1, clinic=clinic)
    original, _ = repo.enqueue(uid, _digest(original_rows), original_rows, uuid4(), config.digest())
    assert repo.process_one() is True

    failed_rows = _rows(day="2026-01-08", count=5, clinic=clinic)
    failed, _ = repo.enqueue(
        uid,
        _digest(failed_rows),
        failed_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=original["upload_id"],
    )
    monkeypatch.setattr(repo, "_persist", lambda *args: (_ for _ in ()).throw(RuntimeError("bad worker")))
    assert repo.process_one() is True
    monkeypatch.undo()
    assert repo.summary(failed["upload_id"], uid, uuid4())["status"] == "failed"

    with psycopg.connect(db[0]) as conn:
        assert conn.execute(
            "SELECT replacement_claimed_by FROM core.appointment_upload WHERE upload_id=%s",
            (original["upload_id"],),
        ).fetchone()[0] is None
    retried = repo.retry(failed["upload_id"], uid, uuid4())
    assert retried["status"] == "pending"
    assert repo.process_one() is True
    assert repo.summary(failed["upload_id"], uid, uuid4())["status"] == "completed"

    # A pending replacement can also be canceled, making the source available
    # for a different explicit revision.
    next_rows = _rows(day="2026-01-09", count=6, clinic=clinic)
    next_upload, _ = repo.enqueue(
        uid,
        _digest(next_rows),
        next_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=failed["upload_id"],
    )
    canceled = repo.soft_delete(next_upload["upload_id"], uid, uuid4())
    assert canceled["deleted_at"] is not None
    final_rows = _rows(day="2026-01-10", count=8, clinic=clinic)
    final_upload, duplicate = repo.enqueue(
        uid,
        _digest(final_rows),
        final_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=failed["upload_id"],
    )
    assert duplicate is False
    assert repo.process_one() is True
    assert repo.summary(final_upload["upload_id"], uid, uuid4())["status"] == "completed"


def test_worker_revalidates_source_before_second_queued_replacement_can_insert(db, appointment_repo):
    repo, uid, config = appointment_repo
    clinic = config.clinic_locations[0]
    original_rows = _rows(count=3, clinic=clinic)
    original, _ = repo.enqueue(uid, _digest(original_rows), original_rows, uuid4(), config.digest())
    assert repo.process_one() is True

    # Simulate an already queued replacement from an older worker/version,
    # then enqueue the current replacement through the guarded repository.
    stale_rows = _rows(day="2026-01-06", count=4, clinic=clinic)
    stale_id = uuid4()
    with psycopg.connect(db[0]) as conn:
        conn.execute(
            """INSERT INTO core.appointment_upload
               (upload_id,uploaded_by,content_hash,mapping_hash,total_rows,replaces_upload_id,created_at,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,now()-interval '1 minute',now()-interval '1 minute')""",
            (stale_id, uid, _digest(stale_rows), config.digest(), len(stale_rows), original["upload_id"]),
        )
        conn.execute(
            "INSERT INTO core.appointment_ingestion_job (upload_id,payload,config_snapshot) VALUES (%s,%s,%s)",
            (
                stale_id,
                Jsonb(stale_rows),
                Jsonb({"categories": config.categories, "clinic_locations": config.clinic_locations}),
            ),
        )

    current_rows = _rows(day="2026-01-07", count=9, clinic=clinic)
    current, duplicate = repo.enqueue(
        uid,
        _digest(current_rows),
        current_rows,
        uuid4(),
        config.digest(),
        replace_upload_id=original["upload_id"],
    )
    assert duplicate is False

    # The stale job is older, so it is selected first.  Its source claim does
    # not match the current replacement and it fails before inserting facts.
    assert repo.process_one() is True
    assert repo.summary(stale_id, uid, uuid4())["status"] == "failed"
    assert repo.process_one() is True
    assert repo.summary(current["upload_id"], uid, uuid4())["status"] == "completed"

    with psycopg.connect(db[0]) as conn:
        active = conn.execute(
            "SELECT source_upload_id,appointment_count FROM analytics.appointment_activity_facts WHERE clinic_location=%s ORDER BY source_upload_id",
            (clinic,),
        ).fetchall()
        assert active == [(current["upload_id"], 9)]


def test_soft_delete_hides_facts_and_physical_removal_is_blocked(db, appointment_repo):
    repo, uid, config = appointment_repo
    rows = _rows(clinic=config.clinic_locations[0])
    upload, _ = repo.enqueue(uid, _digest(rows), rows, uuid4(), config.digest())
    assert repo.process_one() is True
    deleted = repo.soft_delete(upload["upload_id"], uid, uuid4())
    assert deleted["deleted_at"] is not None

    with psycopg.connect(db[1]) as conn:
        assert conn.execute(
            "SELECT count(*) FROM analytics.appointment_activity_facts WHERE source_upload_id=%s",
            (upload["upload_id"],),
        ).fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM core.appointment_upload WHERE upload_id=%s", (upload["upload_id"],))
    with psycopg.connect(db[0]) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM core.appointment_upload WHERE upload_id=%s", (upload["upload_id"],))
