"""Operator-only account creation; no public registration or default password."""
import argparse
import getpass
import os
import re
from uuid import uuid4
import psycopg
from .security import hash_password

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.@+-]{1,100}", args.username):
        parser.error("Invalid username")
    password = getpass.getpass("New password (12–256 characters): ")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords do not match")
    encoded = hash_password(password)
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        user_id = uuid4()
        conn.execute("INSERT INTO core.app_user (user_id,username,password_hash) VALUES (%s,%s,%s)",
                     (user_id,args.username,encoded))
        conn.execute("""INSERT INTO audit.audit_log (actor,action,target,request_id,outcome)
                     VALUES (%s,'account.created','operator-bootstrap',%s,'success')""", (user_id,uuid4()))

if __name__ == "__main__":
    main()
