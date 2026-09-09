"""Populate only an operator-specified date range; no assumed backfill horizon."""
import argparse
from datetime import date, timedelta
import os
import psycopg

def date_rows(start: date, end: date):
    if end < start:
        raise ValueError("End date precedes start date")
    current=start
    while current <= end:
        iso=current.isocalendar()
        yield (int(current.strftime("%Y%m%d")),current,iso.week,
               current-timedelta(days=current.weekday()),iso.year,
               current.month,(current.month-1)//3+1,current.year,iso.weekday)
        if current == end:
            break
        current += timedelta(days=1)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",required=True,type=date.fromisoformat)
    parser.add_argument("--end",required=True,type=date.fromisoformat)
    args=parser.parse_args()
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO analytics.dim_date
                (date_key,full_date,week,week_start,iso_year,month,quarter,year,day_of_week)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                date_rows(args.start,args.end))

if __name__ == "__main__":
    main()
