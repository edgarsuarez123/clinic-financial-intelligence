"""Seed synthetic financial data for development/demo purposes."""
import hashlib, os, random, sys
from datetime import date, timedelta
from uuid import uuid4
import psycopg

DB_URL = os.environ.get("MIGRATION_DATABASE_URL")
if not DB_URL:
    sys.exit("MIGRATION_DATABASE_URL not set")

random.seed(42)

START = date(2025, 1, 1)
END   = date(2026, 9, 30)

CATEGORIES = [
    ("Collections",  "revenue"),
    ("Supplies",     "variable_cost"),
    ("Salary",       "fixed_cost"),
    ("Benefits",     "fixed_cost"),
    ("Rent",         "fixed_cost"),
    ("Utilities",    "fixed_cost"),
    ("Malpractice",  "fixed_cost"),
    ("Software",     "fixed_cost"),
    ("Insurance",    "fixed_cost"),
]

# Baseline monthly revenue. 2026 rows get 8% YoY growth applied.
MONTHLY_REVENUE = {
    1: 185000, 2: 175000, 3: 198000, 4: 205000, 5: 215000, 6: 208000,
    7: 192000, 8: 188000, 9: 202000, 10: 197000, 11: 182000, 12: 168000,
}

# Fixed costs spread evenly across working days of the month
FIXED_MONTHLY = {
    "Salary":      87000,
    "Benefits":    12500,
    "Rent":         8800,
    "Utilities":    2300,
    "Malpractice":  3600,
    "Software":     1900,
    "Insurance":    2600,
}

VARIABLE_RATE = 0.082   # Supplies as fraction of daily revenue

INSURANCES = ["Aetna", "Cigna", "UnitedHealthcare", "Humana", "Triple-S Salud"]
BILLING    = ["99213", "99214", "99203", "99212", "99202"]

def working_days_per_month(start, end):
    counts = {}
    d = start
    while d <= end:
        if d.weekday() < 5:
            counts[(d.year, d.month)] = counts.get((d.year, d.month), 0) + 1
        d += timedelta(days=1)
    return counts

with psycopg.connect(DB_URL) as conn:
    # ── Categories ──────────────────────────────────────────────────────────
    cat_ids = {}
    for name, ctype in CATEGORIES:
        row = conn.execute(
            "SELECT category_key FROM analytics.dim_category WHERE category_name=%s", (name,)
        ).fetchone()
        if row:
            cat_ids[name] = str(row[0])
        else:
            cid = str(uuid4())
            conn.execute(
                "INSERT INTO analytics.dim_category (category_key, category_name, category_type) VALUES (%s,%s,%s)",
                (cid, name, ctype)
            )
            cat_ids[name] = cid
    print(f"Categories ready: {list(cat_ids)}")

    # ── Upload record ────────────────────────────────────────────────────────
    user_id = conn.execute("SELECT user_id FROM core.app_user LIMIT 1").fetchone()[0]
    upload_id  = str(uuid4())
    content_hash = hashlib.sha256(b"synthetic-financial-v2").hexdigest()
    profile_hash = hashlib.sha256(b"synthetic-profile-v1").hexdigest()
    conn.execute("""
        INSERT INTO core.uploads
            (upload_id, filename, uploaded_by, content_hash, status,
             total_rows, rows_accepted, currency, clinic_location, profile_name, profile_hash)
        VALUES (%s,%s,%s,%s,'completed',0,0,'USD','North','synthetic',%s)
    """, (upload_id, "synthetic_financial.csv", user_id, content_hash, profile_hash))

    # ── Revenue upload for insurance dimensions ───────────────────────────────
    upload_ins_id   = str(uuid4())
    content_hash_ins = hashlib.sha256(b"synthetic-insurance-v2").hexdigest()
    conn.execute("""
        INSERT INTO core.uploads
            (upload_id, filename, uploaded_by, content_hash, status,
             total_rows, rows_accepted, currency, clinic_location, profile_name, profile_hash)
        VALUES (%s,%s,%s,%s,'completed',0,0,'USD','North','synthetic-revenue',%s)
    """, (upload_ins_id, "synthetic_insurance.csv", user_id, content_hash_ins, profile_hash))

    # ── Date dimension + transactions ────────────────────────────────────────
    wdays = working_days_per_month(START, END)
    tx_count = 0
    ins_count = 0

    current = START
    while current <= END:
        iso   = current.isocalendar()
        wstart = current - timedelta(days=current.weekday())
        qtr    = (current.month - 1) // 3 + 1
        dkey   = int(current.strftime("%Y%m%d"))

        conn.execute("""
            INSERT INTO analytics.dim_date
                (date_key, full_date, week, week_start, iso_year, month, quarter, year, day_of_week)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
        """, (dkey, current, iso.week, wstart, iso.year, current.month, qtr, current.year, current.weekday()+1))

        if current.weekday() < 5:  # working days only
            n_days = wdays[(current.year, current.month)]
            base   = MONTHLY_REVENUE[current.month]
            if current.year == 2026:
                base = int(base * 1.08)
            # Daily revenue with ±15% noise
            daily_rev = round(base / n_days * (1 + random.uniform(-0.15, 0.15)), 2)

            # Collections (revenue)
            tx_count += 1
            conn.execute("""
                INSERT INTO analytics.transactions
                    (date_key, category_key, type, amount, source_upload_id, source_row)
                VALUES (%s,%s,'revenue',%s,%s,%s)
            """, (dkey, cat_ids["Collections"], daily_rev, upload_id, tx_count))

            # Supplies (variable cost)
            tx_count += 1
            conn.execute("""
                INSERT INTO analytics.transactions
                    (date_key, category_key, type, amount, source_upload_id, source_row)
                VALUES (%s,%s,'expense',%s,%s,%s)
            """, (dkey, cat_ids["Supplies"], round(daily_rev * VARIABLE_RATE, 2), upload_id, tx_count))

            # Fixed costs
            for cat, monthly in FIXED_MONTHLY.items():
                tx_count += 1
                conn.execute("""
                    INSERT INTO analytics.transactions
                        (date_key, category_key, type, amount, source_upload_id, source_row)
                    VALUES (%s,%s,'expense',%s,%s,%s)
                """, (dkey, cat_ids[cat], round(monthly / n_days, 2), upload_id, tx_count))

            # Insurance-tagged revenue rows (split daily revenue across payers/codes)
            splits = random.choices(INSURANCES, k=3)
            codes  = random.choices(BILLING, k=3)
            remain = daily_rev
            for i, (ins, code) in enumerate(zip(splits, codes)):
                share = round(remain * (1/3 if i < 2 else 1), 2) if i < 2 else round(remain, 2)
                remain = round(remain - share, 2)
                ins_count += 1
                conn.execute("""
                    INSERT INTO analytics.transactions
                        (date_key, category_key, type, amount, source_upload_id, source_row,
                         medical_insurance, billing_code)
                    VALUES (%s,%s,'revenue',%s,%s,%s,%s,%s)
                """, (dkey, cat_ids["Collections"], share, upload_ins_id, ins_count, ins, code))

        current += timedelta(days=1)

    # Update row counts on uploads
    conn.execute("UPDATE core.uploads SET total_rows=%s, rows_accepted=%s WHERE upload_id=%s",
                 (tx_count, tx_count, upload_id))
    conn.execute("UPDATE core.uploads SET total_rows=%s, rows_accepted=%s WHERE upload_id=%s",
                 (ins_count, ins_count, upload_ins_id))

    print(f"Seeded {tx_count} financial transactions ({START} → {END})")
    print(f"Seeded {ins_count} insurance revenue rows")
    print("Done.")
