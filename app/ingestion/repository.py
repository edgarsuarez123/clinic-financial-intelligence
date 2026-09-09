from datetime import date
from decimal import Decimal
from uuid import uuid4
from psycopg.types.json import Jsonb
from .validation import rejection
from ..seed_dates import date_rows
from ..store import Store

class UploadConflict(ValueError): pass

class IngestionRepository(Store):
    @staticmethod
    def public(row):
        return {key:row[key] for key in ("upload_id","status","total_rows","rows_accepted", "rows_rejected",
                "rejections","failure_code","currency","profile_name","created_at")}

    def enqueue(self, uid, digest, kind, profile_name, profile, prepared, request_id):
        with self.connect() as c:
            upload_id=uuid4()
            inserted=c.execute("""INSERT INTO core.uploads
                (upload_id,filename,uploaded_by,content_hash,profile_hash,profile_name,currency,
                 total_rows,rows_rejected,rejections)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (content_hash) DO NOTHING RETURNING upload_id""",
                (upload_id,"upload."+kind,uid,digest,profile.digest(),profile_name,profile.currency,
                 prepared.total_rows,len(prepared.rejections),Jsonb(prepared.rejections))).fetchone()
            if not inserted:
                row=c.execute("SELECT * FROM core.uploads WHERE content_hash=%s",(digest,)).fetchone()
                if row["uploaded_by"]!=uid or row["deleted_at"] is not None or row["profile_hash"]!=profile.digest():
                    raise UploadConflict("This content already exists under a different owner, mapping, or deletion state.")
                self._audit(c,uid,"upload.duplicate",str(row["upload_id"]),request_id,"success")
                return self.public(row),True
            c.execute("INSERT INTO core.ingestion_job (upload_id,payload) VALUES (%s,%s)",
                      (upload_id,Jsonb(prepared.rows)))
            self._audit(c,uid,"upload.queued",str(upload_id),request_id,"success")
            row=c.execute("SELECT * FROM core.uploads WHERE upload_id=%s",(upload_id,)).fetchone()
            return self.public(row),False

    def summary(self, upload_id, uid, request_id):
        with self.connect() as c:
            row=c.execute("SELECT * FROM core.uploads WHERE upload_id=%s AND uploaded_by=%s AND deleted_at IS NULL",(upload_id,uid)).fetchone()
            self._audit(c,uid,"upload.summary",str(upload_id),request_id,"success" if row else "denied")
            return self.public(row) if row else None

    def retry(self, upload_id, uid, request_id):
        with self.connect() as c:
            row=c.execute("SELECT * FROM core.uploads WHERE upload_id=%s AND uploaded_by=%s AND deleted_at IS NULL FOR UPDATE",(upload_id,uid)).fetchone()
            if not row:
                self._audit(c,uid,"upload.retry",str(upload_id),request_id,"denied")
                return None
            if row["status"]!="failed": raise UploadConflict("Only failed uploads can be retried.")
            c.execute("UPDATE core.uploads SET status='pending',failure_code=NULL WHERE upload_id=%s",(upload_id,))
            self._audit(c,uid,"upload.retry",str(upload_id),request_id,"success")
            row=c.execute("SELECT * FROM core.uploads WHERE upload_id=%s",(upload_id,)).fetchone()
            return self.public(row)

    def process_one(self):
        # One PostgreSQL transaction owns one job until facts, summary and audit
        # commit together. A dead worker rolls everything back, including locks.
        with self.connect() as c:
            job=c.execute("""SELECT u.*,j.payload FROM core.uploads u
                JOIN core.ingestion_job j USING (upload_id)
                WHERE u.status='pending' AND u.deleted_at IS NULL AND j.deleted_at IS NULL
                ORDER BY u.created_at FOR UPDATE OF u,j SKIP LOCKED LIMIT 1""").fetchone()
            if not job: return False
            c.execute("UPDATE core.ingestion_job SET attempts=attempts+1 WHERE upload_id=%s",(job["upload_id"],))
            try:
                with c.transaction():  # savepoint: never leave partial financial facts
                    self._persist(c,job)
            except Exception:
                c.execute("UPDATE core.uploads SET status='failed',failure_code='processing_failed' WHERE upload_id=%s",(job["upload_id"],))
                self._audit(c,job["uploaded_by"],"upload.failed",str(job["upload_id"]),uuid4(),"error")
            return True

    def _persist(self,c,job):
        rows=job["payload"]
        categories={str(x["category_key"]):x["category_type"] for x in c.execute(
            "SELECT category_key,category_type FROM analytics.dim_category WHERE deleted_at IS NULL").fetchall()}
        providers={str(x["provider_key"]) for x in c.execute(
            "SELECT provider_key FROM analytics.dim_provider WHERE deleted_at IS NULL").fetchall()}
        rejects=list(job["rejections"]); values=[]; days=set()
        for row in rows:
            cat_type=categories.get(row["category_key"])
            reason=None
            if not cat_type:
                reason=("category_unavailable","Mapped category is missing or inactive.")
            elif (cat_type=="revenue") != (row["type"]=="revenue"):
                reason=("category_type_mismatch","Category classification does not match revenue/expense type.")
            elif row["provider_key"] is not None and row["provider_key"] not in providers:
                reason=("provider_unavailable","Mapped provider is missing or inactive.")
            if reason:
                rejects.append(rejection(row["source_row"],row["location"],*reason)); continue
            day=date.fromisoformat(row["date"]); days.add(day)
            values.append((int(day.strftime('%Y%m%d')),row["provider_key"],row["category_key"],row["type"],
                           Decimal(row["amount"]),job["upload_id"],row["source_row"]))
        with c.cursor() as cur:
            cur.executemany("""INSERT INTO analytics.dim_date
                (date_key,full_date,week,week_start,iso_year,month,quarter,year,day_of_week)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                [next(date_rows(day,day)) for day in sorted(days)])
            cur.executemany("""INSERT INTO analytics.transactions
                (date_key,provider_key,category_key,type,amount,source_upload_id,source_row)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",values)
        rejects.sort(key=lambda r:r["source_row"])
        c.execute("""UPDATE core.uploads SET status='completed',rows_accepted=%s,rows_rejected=%s,
                    rejections=%s,failure_code=NULL WHERE upload_id=%s""",
                    (len(values),len(rejects),Jsonb(rejects),job["upload_id"]))
        self._audit(c,job["uploaded_by"],"upload.completed",str(job["upload_id"]),uuid4(),"success")
