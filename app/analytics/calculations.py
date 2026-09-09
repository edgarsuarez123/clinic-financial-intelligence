"""Financial analytics: pure functions using only the Python standard library.

No web/database imports, I/O, global clock, binary-float inputs or currency math.
Missing calendar periods remain unknown; observations are not completeness claims.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, Context, localcontext
from functools import wraps
from typing import Literal

ZERO=Decimal("0")
HUNDRED=Decimal("100")

def exact(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with localcontext(Context(prec=50)):
            return function(*args,**kwargs)
    return wrapped

@dataclass(frozen=True)
class Transaction:
    date: date
    amount: Decimal
    type: Literal["revenue","expense"]
    category_key: str
    category_type: Literal["revenue","fixed_cost","variable_cost"]
    provider_key: str | None = None

    def __post_init__(self):
        if type(self.date) is not date:
            raise ValueError("Transaction date must be a calendar date")
        if not isinstance(self.amount,Decimal) or not self.amount.is_finite():
            raise ValueError("Amounts must be finite Decimal values")
        if self.amount.copy_abs() >= Decimal("10000000000000000"):
            raise ValueError("Amount exceeds the supported transaction bound")
        with localcontext(Context(prec=50)):
            if self.amount != self.amount.quantize(Decimal("0.01")):
                raise ValueError("Fractional cents are not valid transaction inputs")
        if self.type not in {"revenue","expense"} or self.category_type not in {"revenue","fixed_cost","variable_cost"}:
            raise ValueError("Unknown transaction classification")
        if (self.type=="revenue") != (self.category_type=="revenue"):
            raise ValueError("Category and transaction types disagree")
        if not self.category_key:
            raise ValueError("Category identity is required")

@dataclass(frozen=True)
class CostCoverage:
    start: date
    end: date
    basis: str

    def __post_init__(self):
        if self.end<self.start or not self.basis.strip():
            raise ValueError("Cost coverage requires a valid range and explicit basis")

@exact
def percentage(numerator,denominator):
    return numerator/denominator*HUNDRED if denominator>ZERO else None

@exact
def growth(current,previous):
    if current is None or previous is None or previous<=ZERO:
        return None
    return (current-previous)/previous*HUNDRED

@exact
def coefficient_of_variation(values):
    if any(not isinstance(v,Decimal) or not v.is_finite() for v in values):
        raise ValueError("Volatility inputs must be finite Decimals")
    count=len(values)
    if count<2: return {"value":None,"samples":count,"reason":"fewer_than_two_periods"}
    mean=sum(values,ZERO)/Decimal(count)
    if mean==ZERO: return {"value":None,"samples":count,"reason":"zero_mean"}
    variance=sum(((v-mean)**2 for v in values),ZERO)/Decimal(count)
    return {"value":variance.sqrt()/abs(mean),"samples":count,"reason":None}

@exact
def summarize(rows):
    rows=tuple(rows)
    if not rows:
        return {"observed":False,"row_count":0,"revenue":None,"expense":None,"net":None,
                "margin_pct":None,"fixed_cost":None,"variable_cost":None,"categories":[]}
    revenue=sum((r.amount for r in rows if r.type=="revenue"),ZERO)
    expense=sum((r.amount for r in rows if r.type=="expense"),ZERO)
    category_totals=defaultdict(lambda:ZERO)
    fixed=ZERO; variable=ZERO
    for row in rows:
        if row.type=="expense":
            category_totals[(row.category_key,row.category_type)]+=row.amount
            if row.category_type=="fixed_cost": fixed+=row.amount
            else: variable+=row.amount
    return {"observed":True,"row_count":len(rows),"revenue":revenue,"expense":expense,
        "net":revenue-expense,"margin_pct":percentage(revenue-expense,revenue),
        "fixed_cost":fixed,"variable_cost":variable,
        "categories":[{"category_key":key,"category_type":kind,"amount":amount,
                       "pct_revenue":percentage(amount,revenue)}
                      for (key,kind),amount in sorted(category_totals.items())]}

def period_start(day,frequency):
    if frequency=="week": return day-timedelta(days=day.weekday())
    if frequency=="month": return day.replace(day=1)
    raise ValueError("Frequency must be week or month")

def next_period(start,frequency):
    if frequency=="week": return start+timedelta(days=7)
    if frequency=="month":
        return date(start.year+(start.month==12),1 if start.month==12 else start.month+1,1)
    raise ValueError("Frequency must be week or month")

def check_range(start,end):
    if type(start) is not date or type(end) is not date or end<start:
        raise ValueError("A valid inclusive date range is required")
    if start.year<1900 or end.year>2199 or (end-start).days>3660:
        raise ValueError("Use a range of at most ten years between 1900 and 2199")

@exact
def moving_average(series,index,field,window):
    if window<1: raise ValueError("Window must be positive")
    sample=series[max(0,index-window+1):index+1]
    known=[r[field] for r in sample if r["observed"]]
    return {"value":sum(known,ZERO)/Decimal(len(known)) if known else None,
            "observed_periods":len(known),"calendar_periods":len(sample),"target_periods":window,
            "complete_window":len(sample)==window and len(known)==window and not any(r["partial"] for r in sample)}

@exact
def period_series(rows,start,end,frequency):
    check_range(start,end)
    groups=defaultdict(list)
    for row in rows:
        if start<=row.date<=end: groups[period_start(row.date,frequency)].append(row)
    series=[]; current=period_start(start,frequency)
    while current<=end:
        following=next_period(current,frequency)
        last=following-timedelta(days=1)
        series.append({"period_start":current,"period_end":last,
            "coverage_start":max(start,current),"coverage_end":min(end,last),
            "partial":current<start or last>end,**summarize(groups[current])})
        current=following
    for index,item in enumerate(series):
        previous=series[index-1] if index else None
        comparable=previous is not None and not item["partial"] and not previous["partial"] and item["observed"] and previous["observed"]
        item["revenue_growth_pct"]=growth(item["revenue"],previous["revenue"]) if comparable else None
        item["expense_growth_pct"]=growth(item["expense"],previous["expense"]) if comparable else None
        item["growth_comparable"]=bool(comparable)
        if frequency=="week":
            for window in (4,12):
                item[f"revenue_ma_{window}"]=moving_average(series,index,"revenue",window)
                item[f"expense_ma_{window}"]=moving_average(series,index,"expense",window)
    return series

@exact
def analytics(rows,start,end):
    check_range(start,end)
    selected=tuple(r for r in rows if start<=r.date<=end)
    weekly=period_series(selected,start,end,"week")
    monthly=period_series(selected,start,end,"month")
    eligible=[r for r in weekly if r["observed"] and not r["partial"]]
    return {"start":start,"end":end,"summary":summarize(selected),"weekly":weekly,"monthly":monthly,
        "volatility":{"frequency":"week","basis":"Observed, untrimmed calendar weeks; population standard deviation divided by absolute mean.",
            "revenue":coefficient_of_variation([r["revenue"] for r in eligible]),
            "expense":coefficient_of_variation([r["expense"] for r in eligible]),
            "missing_weeks":sum(not r["observed"] for r in weekly),
            "partial_weeks":sum(r["partial"] for r in weekly)},
        "data_notes":["Totals describe imported records, not a certification of complete books.",
            "No-row periods are unknown, not zero; no activity is imputed.",
            "Weeks start Monday. Months follow the calendar. Dates are inclusive.",
            "Moving averages use observed values in the trailing 4/12 calendar weeks; counts and partial windows are shown.",
            "Growth requires adjacent observed, untrimmed periods and a positive prior denominator.",
            "Margins and expense/revenue percentages are undefined when revenue is nonpositive."]}

@exact
def provider_contributions(rows,start,end,cost_coverage):
    check_range(start,end)
    groups=defaultdict(list); unassigned=[]
    for row in rows:
        if start<=row.date<=end:
            if row.provider_key is None: unassigned.append(row)
            else: groups[row.provider_key].append(row)
    results=[]
    for key,group in sorted(groups.items()):
        totals=summarize(group); coverage=cost_coverage.get(key)
        confirmed=coverage is not None and coverage.start<=start and coverage.end>=end
        cost=totals["expense"] if confirmed else None
        results.append({"provider_key":key,"revenue":totals["revenue"],"attributed_expense":totals["expense"],
            "fully_loaded_cost":cost,"contribution":totals["revenue"]-cost if confirmed else None,
            "contribution_margin_pct":percentage(totals["revenue"]-cost,totals["revenue"]) if confirmed else None,
            "cost_complete":confirmed,"cost_basis":coverage.basis if confirmed else None,
            "status":"computed" if confirmed else "fully_loaded_cost_not_confirmed"})
    return {"start":start,"end":end,"providers":results,"unattributed":summarize(unassigned),
        "notes":["No practice-level expenses or revenue are allocated to providers automatically.",
                 "Fully loaded cost is computed from attributed expense records only when explicitly confirmed for the whole selected range."]}
