"""Forward-only, transactional SQL migrations; run with separate owner credentials."""
import hashlib
import os
from pathlib import Path
import psycopg

ROOT = Path(__file__).resolve().parent.parent / "migrations"

def migrate(dsn, directory=ROOT):
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(482710031)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS migrations")
        conn.execute("""CREATE TABLE IF NOT EXISTS migrations.applied (
            name text PRIMARY KEY, sha256 text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())""")
        applied = dict(conn.execute("SELECT name,sha256 FROM migrations.applied").fetchall())
        files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
        names = {f.name for f in files}
        if set(applied) - names:
            raise RuntimeError("Previously applied migration is missing")
        for path in files:
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError("Applied migration has changed: " + path.name)
                continue
            if applied and path.name < max(applied):
                raise RuntimeError("Cannot insert a migration before applied history")
            conn.execute(content.decode())
            conn.execute("INSERT INTO migrations.applied (name,sha256) VALUES (%s,%s)", (path.name,checksum))

if __name__ == "__main__":
    migrate(os.environ["MIGRATION_DATABASE_URL"])
