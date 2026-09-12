"""PostgreSQL repository for queued appointment aggregate imports and reads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..store import Store
from .aggregation import AppointmentFact
from .config import AppointmentConfig


class AppointmentUploadConflict(ValueError):
    """The source hash already belongs to a different upload identity."""


class AppointmentProcessingError(ValueError):
    """A queued normalized row cannot be safely persisted."""


class AppointmentRepository(Store):
    MAX_ROWS = 250_000

    def __init__(self, settings, config: AppointmentConfig | None = None):
        super().__init__(settings)
        self.config = config or AppointmentConfig()

    @staticmethod
    def public(row):
        if not row:
            return None
        return {
            key: row[key]
            for key in (
                "upload_id",
                "content_hash",
                "source_hash",
                "replaces_upload_id",
                "status",
                "total_rows",
                "rows_accepted",
                "rows_rejected",
                "rejections",
                "failure_code",
                "created_at",
                "updated_at",
                "deleted_at",
            )
        }

    def enqueue(
        self,
        uid,
        content_hash: str,
        rows: list[dict[str, object]],
        request_id,
        mapping_hash: str | None = None,
        replace_upload_id: UUID | None = None,
        source_hash: str | None = None,
    ):
        """Queue one normalized batch, atomically with its audit record."""

        if not rows or len(rows) > 5000:
            raise ValueError("Appointment imports must contain 1–5000 rows")
        if len(content_hash) != 64 or any(ch not in "0123456789abcdef" for ch in content_hash):
            raise ValueError("Invalid canonical appointment content hash")
        if source_hash is not None and (
            len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash)
        ):
            raise ValueError("Invalid appointment source hash")
        mapping_hash = mapping_hash or self.config.digest()
        if len(mapping_hash) != 64 or any(ch not in "0123456789abcdef" for ch in mapping_hash):
            raise ValueError("Invalid appointment mapping hash")
        with self.connect() as c:
            upload_id = uuid4()
            inserted = c.execute(
                """INSERT INTO core.appointment_upload
                    (upload_id,uploaded_by,content_hash,source_hash,mapping_hash,total_rows,replaces_upload_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (content_hash) DO NOTHING RETURNING *""",
                (upload_id, uid, content_hash, source_hash, mapping_hash, len(rows), replace_upload_id),
            ).fetchone()
            if not inserted:
                row = c.execute(
                    "SELECT * FROM core.appointment_upload WHERE content_hash=%s",
                    (content_hash,),
                ).fetchone()
                # The replacement relationship is part of the canonical
                # upload identity.  A repeat of a completed replacement must
                # therefore be an idempotent duplicate, while the same
                # content requested against a different source is a conflict.
                if (
                    row["uploaded_by"] != uid
                    or row["mapping_hash"] != mapping_hash
                    or row["deleted_at"] is not None
                    or row["replaces_upload_id"] != replace_upload_id
                ):
                    raise AppointmentUploadConflict(
                        "This appointment batch already exists under a different owner, mapping, or deletion state."
                    )
                self._audit(c, uid, "appointment.upload.duplicate", str(row["upload_id"]), request_id, "success")
                return self.public(row), True
            if replace_upload_id is not None:
                replacement = c.execute(
                    """UPDATE core.appointment_upload
                       SET replacement_claimed_by=%s
                       WHERE upload_id=%s AND uploaded_by=%s AND status='completed'
                         AND deleted_at IS NULL AND replacement_claimed_by IS NULL
                       RETURNING upload_id""",
                    (upload_id, replace_upload_id, uid),
                ).fetchone()
                if not replacement:
                    raise AppointmentUploadConflict(
                        "Only your completed appointment import can be explicitly replaced, and it may have one pending replacement."
                    )
            c.execute(
                """INSERT INTO core.appointment_ingestion_job
                   (upload_id,payload,config_snapshot) VALUES (%s,%s,%s)""",
                (
                    upload_id,
                    Jsonb(rows),
                    Jsonb(
                        {
                            "categories": self.config.categories,
                            "clinic_locations": self.config.clinic_locations,
                        }
                    ),
                ),
            )
            self._audit(c, uid, "appointment.upload.queued", str(upload_id), request_id, "success")
            row = c.execute(
                "SELECT * FROM core.appointment_upload WHERE upload_id=%s", (upload_id,)
            ).fetchone()
            return self.public(row), False

    def summary(self, upload_id: UUID, uid, request_id):
        with self.connect() as c:
            row = c.execute(
                """SELECT * FROM core.appointment_upload
                   WHERE upload_id=%s AND uploaded_by=%s AND deleted_at IS NULL""",
                (upload_id, uid),
            ).fetchone()
            self._audit(c, uid, "appointment.upload.summary", str(upload_id), request_id, "success" if row else "denied")
            return self.public(row) if row else None

    def retry(self, upload_id: UUID, uid, request_id):
        with self.connect() as c:
            row = c.execute(
                """SELECT * FROM core.appointment_upload
                   WHERE upload_id=%s AND uploaded_by=%s AND deleted_at IS NULL FOR UPDATE""",
                (upload_id, uid),
            ).fetchone()
            if not row:
                self._audit(c, uid, "appointment.upload.retry", str(upload_id), request_id, "denied")
                return None
            if row["status"] != "failed":
                self._audit(c, uid, "appointment.upload.retry", str(upload_id), request_id, "denied")
                raise AppointmentUploadConflict("Only failed appointment uploads can be retried.")
            replacement = row["replaces_upload_id"]
            if replacement is not None:
                # A failed replacement releases its source claim in
                # process_one.  Reclaim it while holding both rows so a
                # retry cannot race a new replacement or a source deletion.
                old = c.execute(
                    """SELECT upload_id,status,deleted_at,replacement_claimed_by,uploaded_by
                       FROM core.appointment_upload WHERE upload_id=%s FOR UPDATE""",
                    (replacement,),
                ).fetchone()
                if (
                    not old
                    or old["uploaded_by"] != uid
                    or old["status"] != "completed"
                    or old["deleted_at"] is not None
                    or old["replacement_claimed_by"] not in (None, upload_id)
                ):
                    self._audit(c, uid, "appointment.upload.retry", str(upload_id), request_id, "denied")
                    raise AppointmentUploadConflict(
                        "The original appointment source is no longer available for retry."
                    )
                claimed = c.execute(
                    """UPDATE core.appointment_upload
                       SET replacement_claimed_by=%s
                       WHERE upload_id=%s AND status='completed' AND deleted_at IS NULL
                         AND replacement_claimed_by IS NULL
                       RETURNING upload_id""",
                    (upload_id, replacement),
                ).fetchone()
                if not claimed and old["replacement_claimed_by"] != upload_id:
                    self._audit(c, uid, "appointment.upload.retry", str(upload_id), request_id, "denied")
                    raise AppointmentUploadConflict(
                        "Another appointment replacement already claims the original source."
                    )
            c.execute(
                "UPDATE core.appointment_upload SET status='pending',failure_code=NULL WHERE upload_id=%s",
                (upload_id,),
            )
            self._audit(c, uid, "appointment.upload.retry", str(upload_id), request_id, "success")
            return self.public(c.execute("SELECT * FROM core.appointment_upload WHERE upload_id=%s", (upload_id,)).fetchone())

    def soft_delete(self, upload_id: UUID, uid, request_id):
        """Soft-delete a source and its facts; physical removal is prohibited."""

        with self.connect() as c:
            row = c.execute(
                """SELECT * FROM core.appointment_upload
                   WHERE upload_id=%s AND uploaded_by=%s AND deleted_at IS NULL FOR UPDATE""",
                (upload_id, uid),
            ).fetchone()
            if not row:
                self._audit(c, uid, "appointment.upload.delete", str(upload_id), request_id, "denied")
                return None
            replacement = row["replaces_upload_id"]
            if replacement is not None:
                # Canceling a queued replacement must release its source so a
                # revised replacement can be queued immediately.  The source
                # row is locked by this update after the child row lock above,
                # matching retry's lock order.
                c.execute(
                    """UPDATE core.appointment_upload
                       SET replacement_claimed_by=NULL
                       WHERE upload_id=%s AND replacement_claimed_by=%s""",
                    (replacement, upload_id),
                )
            c.execute("UPDATE analytics.appointment_activity SET deleted_at=now() WHERE source_upload_id=%s AND deleted_at IS NULL", (upload_id,))
            c.execute("UPDATE core.appointment_ingestion_job SET deleted_at=now() WHERE upload_id=%s AND deleted_at IS NULL", (upload_id,))
            updated = c.execute(
                "UPDATE core.appointment_upload SET deleted_at=now(), replacement_claimed_by=NULL WHERE upload_id=%s RETURNING *",
                (upload_id,),
            ).fetchone()
            self._audit(c, uid, "appointment.upload.delete", str(upload_id), request_id, "success")
            return self.public(updated or row)

    def process_one(self):
        """Process one queued job.  Facts, status and audit commit together."""

        with self.connect() as c:
            job = c.execute(
                """SELECT u.*,j.payload,j.config_snapshot
                   FROM core.appointment_upload u
                   JOIN core.appointment_ingestion_job j USING (upload_id)
                   WHERE u.status='pending' AND u.deleted_at IS NULL AND j.deleted_at IS NULL
                   ORDER BY u.created_at FOR UPDATE OF u,j SKIP LOCKED LIMIT 1"""
            ).fetchone()
            if not job:
                return False
            c.execute(
                "UPDATE core.appointment_upload SET status='processing' WHERE upload_id=%s",
                (job["upload_id"],),
            )
            c.execute(
                "UPDATE core.appointment_ingestion_job SET attempts=attempts+1 WHERE upload_id=%s",
                (job["upload_id"],),
            )
            try:
                # A savepoint ensures a malformed worker payload never leaves
                # partial appointment facts behind.
                with c.transaction():
                    self._persist(c, job)
            except Exception:
                replacement = job.get("replaces_upload_id")
                if replacement is not None:
                    c.execute(
                        """UPDATE core.appointment_upload
                           SET replacement_claimed_by=NULL
                           WHERE upload_id=%s AND replacement_claimed_by=%s""",
                        (replacement, job["upload_id"]),
                    )
                c.execute(
                    "UPDATE core.appointment_upload SET status='failed',failure_code='processing_failed' WHERE upload_id=%s",
                    (job["upload_id"],),
                )
                self._audit(c, job["uploaded_by"], "appointment.upload.failed", str(job["upload_id"]), uuid4(), "error")
            return True

    def _persist(self, c, job):
        payload = job["payload"]
        if not isinstance(payload, list) or not payload:
            raise AppointmentProcessingError("Appointment worker payload is empty")
        snapshot = job.get("config_snapshot") or {}
        if not isinstance(snapshot, dict):
            raise AppointmentProcessingError("Appointment worker configuration snapshot is invalid")
        categories = snapshot.get("categories")
        clinics = snapshot.get("clinic_locations")
        if not isinstance(categories, dict) or not categories:
            raise AppointmentProcessingError("Appointment worker configuration snapshot is missing categories")
        if not isinstance(clinics, list) or not clinics:
            raise AppointmentProcessingError("Appointment worker configuration snapshot is missing clinic locations")
        values = []
        source_rows = set()
        for row in payload:
            if not isinstance(row, dict):
                raise AppointmentProcessingError("Appointment worker payload is invalid")
            if set(row) - {
                "source_row", "date", "clinic_location", "category",
                "appointment_count", "billed_amount", "collected_amount",
            }:
                raise AppointmentProcessingError("Appointment worker payload contains unsupported fields")
            category = row.get("category")
            if not isinstance(category, str) or category not in categories:
                raise AppointmentProcessingError("Queued row uses an inactive appointment category")
            try:
                day = date.fromisoformat(str(row["date"]))
                clinic = row["clinic_location"]
                if not isinstance(clinic, str) or clinic not in clinics:
                    raise ValueError
                count = row["appointment_count"]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > 2147483647:
                    raise ValueError
                billed = None if row.get("billed_amount") is None else Decimal(str(row["billed_amount"]))
                collected = None if row.get("collected_amount") is None else Decimal(str(row["collected_amount"]))
                if any(
                    value is not None
                    and (
                        not value.is_finite()
                        or abs(value) >= Decimal("10000000000000000")
                        or value.as_tuple().exponent < -2
                    )
                    for value in (billed, collected)
                ):
                    raise ValueError
                source_row = row["source_row"]
                if isinstance(source_row, bool) or not isinstance(source_row, int) or source_row <= 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
                raise AppointmentProcessingError("Queued row is not a normalized appointment aggregate") from exc
            if source_row in source_rows:
                raise AppointmentProcessingError("Queued appointment source rows must be unique")
            source_rows.add(source_row)
            values.append((day, clinic, category, count, billed, collected, job["upload_id"], source_row))

        # Category labels are configuration, not a classification inferred
        # from billing codes.  Upsert only these approved canonical keys.
        replacement = job.get("replaces_upload_id")
        if replacement is not None:
            old = c.execute(
                """SELECT upload_id,uploaded_by,status,deleted_at,replacement_claimed_by
                   FROM core.appointment_upload WHERE upload_id=%s FOR UPDATE""",
                (replacement,),
            ).fetchone()
            if (
                not old
                or old["uploaded_by"] != job["uploaded_by"]
                or old["status"] != "completed"
                or old["deleted_at"] is not None
                or old["replacement_claimed_by"] != job["upload_id"]
            ):
                raise AppointmentProcessingError("The explicit replacement source is no longer available")
        with c.cursor() as cur:
            cur.executemany(
                """INSERT INTO analytics.appointment_category (category_key,label)
                   VALUES (%s,%s) ON CONFLICT (category_key) DO UPDATE SET label=EXCLUDED.label,deleted_at=NULL""",
                [(key, label) for key, label in categories.items()],
            )
            cur.executemany(
                """INSERT INTO analytics.appointment_activity
                   (activity_date,clinic_location,category_key,appointment_count,billed_amount,collected_amount,source_upload_id,source_row)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                values,
            )

        if replacement is not None:
            c.execute(
                "UPDATE analytics.appointment_activity SET deleted_at=now() WHERE source_upload_id=%s AND deleted_at IS NULL",
                (replacement,),
            )
            c.execute(
                "UPDATE core.appointment_ingestion_job SET deleted_at=now() WHERE upload_id=%s AND deleted_at IS NULL",
                (replacement,),
            )
            replaced = c.execute(
                """UPDATE core.appointment_upload
                   SET deleted_at=now(), replacement_claimed_by=NULL
                   WHERE upload_id=%s AND deleted_at IS NULL AND replacement_claimed_by=%s
                   RETURNING upload_id""",
                (replacement, job["upload_id"]),
            ).fetchone()
            if not replaced:
                raise AppointmentProcessingError("The explicit replacement source changed during processing")
            self._audit(
                c,
                job["uploaded_by"],
                "appointment.upload.replaced",
                f"{replacement}:{job['upload_id']}",
                uuid4(),
                "success",
            )
        c.execute(
            """UPDATE core.appointment_upload
               SET status='completed',rows_accepted=%s,rows_rejected=0,rejections='[]'::jsonb,failure_code=NULL
               WHERE upload_id=%s""",
            (len(values), job["upload_id"]),
        )
        self._audit(c, job["uploaded_by"], "appointment.upload.completed", str(job["upload_id"]), uuid4(), "success")

    def rows(
        self,
        uid,
        request_id,
        start: date,
        end: date,
        *,
        clinic_location: str | None = None,
        category: str | None = None,
    ) -> list[AppointmentFact]:
        with self.connect() as c:
            records = c.execute(
                """SELECT activity_date,clinic_location,category_key,appointment_count,billed_amount,collected_amount
                   FROM analytics.appointment_activity_facts
                   WHERE activity_date BETWEEN %s AND %s
                     AND (%s::text IS NULL OR clinic_location=%s)
                     AND (%s::text IS NULL OR category_key=%s)
                   ORDER BY activity_date,clinic_location,category_key,source_row
                   LIMIT %s""",
                (start, end, clinic_location, clinic_location, category, category, self.MAX_ROWS + 1),
            ).fetchall()
            self._audit(c, uid, "appointment.report", "appointment-activity", request_id, "success")
        if len(records) > self.MAX_ROWS:
            raise ValueError("This appointment range is too large; select a smaller date range.")
        return [
            AppointmentFact(
                activity_date=row["activity_date"],
                clinic_location=row["clinic_location"],
                category=row["category_key"],
                appointment_count=row["appointment_count"],
                billed_amount=row["billed_amount"],
                collected_amount=row["collected_amount"],
            )
            for row in records
        ]

    def metadata(self, uid, request_id):
        with self.connect() as c:
            row = c.execute(
                """SELECT min(activity_date) AS first_date,max(activity_date) AS last_date,
                   count(*) AS row_count,
                   array_agg(DISTINCT clinic_location) AS clinic_locations,
                   array_agg(DISTINCT category_key) AS categories
                   FROM analytics.appointment_activity_facts"""
            ).fetchone()
            self._audit(c, uid, "appointment.metadata", "appointment-activity", request_id, "success")
        row["clinic_locations"] = sorted(row["clinic_locations"] or [])
        row["categories"] = sorted(row["categories"] or [])
        return row
