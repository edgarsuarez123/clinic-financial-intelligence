from ..store import Store
from .calculations import Transaction

class DataUnavailable(ValueError):
    def __init__(self,code,message): self.code=code; super().__init__(message)

class AnalyticsRepository(Store):
    MAX_ROWS=250000

    def revenue_rows(self,uid,request_id,start,end,clinic_location=None):
        with self.connect() as c:
            records=c.execute("SELECT * FROM analytics.revenue_facts WHERE full_date BETWEEN %s AND %s AND (%s::text IS NULL OR coalesce(clinic_location,'Unassigned')=%s) LIMIT %s",
                              (start,end,clinic_location,clinic_location,self.MAX_ROWS+1)).fetchall()
            self._audit(c,uid,'analytics.revenue','revenue',request_id,'success')
        if len(records)>self.MAX_ROWS:
            raise DataUnavailable('range_too_large','Select a smaller date range; this request exceeds 250,000 rows.')
        currencies={r['currency'] for r in records}
        if currencies and (None in currencies or len(currencies)!=1):
            raise DataUnavailable('currency_unconfirmed','Confirm the source currency before revenue analysis.')
        return records,next(iter(currencies)) if currencies else None

    def metadata(self,uid,request_id):
        with self.connect() as c:
            row=c.execute("""SELECT min(full_date) AS first_date,max(full_date) AS last_date,
                count(*) AS row_count, array_agg(DISTINCT coalesce(clinic_location,'Unassigned')) AS clinic_locations FROM analytics.dashboard_facts""").fetchone()
            row['clinic_locations']=sorted(row['clinic_locations'] or [])
            self._audit(c,uid,"analytics.metadata","dashboard",request_id,"success")
            return row

    def rows(self,uid,request_id,start,end,providers=False,clinic_location=None):
        # The only dynamic SQL choice is a fixed, internal pair of query strings.
        statement=("SELECT * FROM analytics.provider_facts WHERE full_date BETWEEN %s AND %s AND (%s::text IS NULL OR coalesce(clinic_location,'Unassigned')=%s) LIMIT %s"
                   if providers else
                   "SELECT * FROM analytics.dashboard_facts WHERE full_date BETWEEN %s AND %s AND (%s::text IS NULL OR coalesce(clinic_location,'Unassigned')=%s) LIMIT %s")
        with self.connect() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            records=c.execute(statement,(start,end,clinic_location,clinic_location,self.MAX_ROWS+1)).fetchall()
            self._audit(c,uid,"analytics.providers" if providers else "analytics.dashboard",
                        "financial-data",request_id,"success")
        if len(records)>self.MAX_ROWS:
            raise DataUnavailable("range_too_large","Select a smaller date range; this request exceeds 250,000 rows.")
        currencies={r['currency'] for r in records}
        if currencies and (None in currencies or len(currencies)!=1):
            raise DataUnavailable("currency_unconfirmed","This range has missing or mixed currency metadata. Confirm the source currency before analysis.")
        try:
            rows=[Transaction(date=r['full_date'],amount=r['amount'],type=r['type'],
                   category_key=str(r['category_key']),category_type=r['category_type'],
                   provider_key=str(r['provider_key']) if providers and r['provider_key'] is not None else None)
                   for r in records]
        except ValueError:
            raise DataUnavailable("inconsistent_classification","Imported facts and category classification disagree; review the data before analysis.") from None
        return rows,next(iter(currencies)) if currencies else None

    def locations(self,uid,request_id,start,end):
        with self.connect() as c:
            rows=c.execute("""SELECT coalesce(clinic_location,'Unassigned') AS clinic_location,currency,
                sum(CASE WHEN type='revenue' THEN amount ELSE 0 END) AS revenue,
                sum(CASE WHEN type='expense' THEN amount ELSE 0 END) AS expense,
                sum(CASE WHEN type='revenue' THEN amount ELSE -amount END) AS net
                FROM analytics.dashboard_facts WHERE full_date BETWEEN %s AND %s
                GROUP BY clinic_location,currency ORDER BY clinic_location,currency""",(start,end)).fetchall()
            self._audit(c,uid,'analytics.locations','locations',request_id,'success')
        return rows
