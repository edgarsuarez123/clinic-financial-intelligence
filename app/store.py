from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

class Store:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def connect(self):
        with psycopg.connect(self.settings.database_url, row_factory=dict_row,
                             connect_timeout=5, options="-c statement_timeout=5000") as conn:
            yield conn

    def check_runtime(self):
        with self.connect() as conn:
            row = conn.execute("""
                SELECT current_user AS name, rolsuper, rolcreatedb, rolcreaterole
                FROM pg_roles WHERE rolname = current_user
            """).fetchone()
            if row["name"] != "clinic_app" or any(row[k] for k in ("rolsuper", "rolcreatedb", "rolcreaterole")):
                raise RuntimeError("API requires the restricted clinic_app database role")
            conn.execute("SELECT user_id FROM core.app_user LIMIT 0")

    def audit(self, actor, action, target, request_id, outcome="success"):
        with self.connect() as conn:
            self._audit(conn, actor, action, target, request_id, outcome)

    @staticmethod
    def _audit(conn, actor, action, target, request_id, outcome):
        conn.execute("""INSERT INTO audit.audit_log
            (actor, action, target, request_id, outcome) VALUES (%s,%s,%s,%s,%s)""",
            (actor, action, target, request_id, outcome))

    def login_allowed(self, username):
        # Shared, database-backed throttling across API workers. Unknown users
        # use the same code path. Raw usernames are not retained in this table.
        from .security import token_hash
        from datetime import datetime, timezone, timedelta
        key = token_hash(username)
        with self.connect() as conn:
            conn.execute("INSERT INTO core.login_throttle (key) VALUES (%s) ON CONFLICT DO NOTHING", (key,))
            row = conn.execute("SELECT * FROM core.login_throttle WHERE key=%s FOR UPDATE", (key,)).fetchone()
            now = datetime.now(timezone.utc)
            if now - row["window_start"] >= timedelta(seconds=self.settings.login_window_seconds):
                conn.execute("UPDATE core.login_throttle SET attempts=1, window_start=%s WHERE key=%s", (now,key))
                return True
            if row["attempts"] >= self.settings.login_limit:
                return False
            conn.execute("UPDATE core.login_throttle SET attempts=attempts+1 WHERE key=%s", (key,))
            return True

    def find_user(self, username):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM core.app_user WHERE username=%s AND deleted_at IS NULL",
                                (username,)).fetchone()

    def create_session(self, user_id, digest, expires_at, request_id):
        with self.connect() as conn:
            # Recheck active state while serializing against account deactivation.
            row = conn.execute("SELECT user_id FROM core.app_user WHERE user_id=%s AND deleted_at IS NULL FOR UPDATE", (user_id,)).fetchone()
            if not row:
                return False
            conn.execute("INSERT INTO core.auth_session (token_hash,user_id,expires_at) VALUES (%s,%s,%s)",
                         (digest,user_id,expires_at))
            self._audit(conn,user_id,"auth.login","auth",request_id,"success")
            return True

    def resolve_session(self, digest):
        with self.connect() as conn:
            return conn.execute("""SELECT u.user_id, u.username FROM core.auth_session s
                JOIN core.app_user u USING (user_id)
                WHERE s.token_hash=%s AND s.deleted_at IS NULL AND s.expires_at > now()
                AND u.deleted_at IS NULL""", (digest,)).fetchone()

    def revoke_session(self, digest, actor, request_id):
        with self.connect() as conn:
            conn.execute("UPDATE core.auth_session SET deleted_at=now(), updated_at=now() WHERE token_hash=%s AND deleted_at IS NULL", (digest,))
            self._audit(conn,actor,"auth.logout","auth",request_id,"success")

    def ready(self):
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
