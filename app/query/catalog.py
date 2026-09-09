"""Reviewed parameterized SELECT catalog: untrusted SQL is never executed directly."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from ..analytics.calculations import check_range

@dataclass(frozen=True)
class Query:
    key: str
    description: str
    sql: str
    columns: tuple[str,...]
    provider_access: bool=False

TOTALS="""sum(revenue) AS revenue, sum(expense) AS expense,
    sum(revenue)-sum(expense) AS net,
    (sum(revenue)-sum(expense))*100/nullif(greatest(sum(revenue),0),0) AS margin_pct"""
WINDOW="full_date BETWEEN %(start)s AND %(end)s"
# These fragments are trusted source constants; question text and date values are bound separately.
CATALOG={q.key:q for q in (
    Query('summary','Total revenue, recorded expense, net and margin over the selected dates.',
        f'SELECT currency, {TOTALS} FROM analytics.nl_practice_daily WHERE {WINDOW} GROUP BY currency ORDER BY currency',
        ('currency','revenue','expense','net','margin_pct')),
    Query('monthly','Observed monthly revenue, expense, net, margin and adjacent observed-month revenue growth. Missing months are not zero.',
        f'''WITH totals AS (SELECT year,month,currency,sum(revenue) AS revenue,sum(expense) AS expense,
        (make_date(year,month,1)>=%(start)s AND (make_date(year,month,1)+interval '1 month'-interval '1 day')::date<=%(end)s) AS selected_full_month
        FROM analytics.nl_practice_daily WHERE {WINDOW} GROUP BY year,month,currency)
        SELECT year,month,currency,revenue,expense,revenue-expense AS net,
        (revenue-expense)*100/nullif(greatest(revenue,0),0) AS margin_pct,
        CASE WHEN selected_full_month AND lag(selected_full_month) OVER w
             AND (year*12+month)-lag(year*12+month) OVER w=1
             AND lag(revenue) OVER w>0 THEN (revenue-lag(revenue) OVER w)*100/lag(revenue) OVER w END AS revenue_growth_pct
        FROM totals WINDOW w AS (PARTITION BY currency ORDER BY year,month) ORDER BY year,month,currency''',
        ('year','month','currency','revenue','expense','net','margin_pct','revenue_growth_pct')),
    Query('weekly','Observed weekly revenue, expense, net and margin, grouped by ISO week start.',
        f'SELECT week_start,currency,{TOTALS} FROM analytics.nl_practice_daily WHERE {WINDOW} GROUP BY week_start,currency ORDER BY week_start,currency',
        ('week_start','currency','revenue','expense','net','margin_pct')),
    Query('cost_breakdown','Fixed and variable recorded costs, and each as a percentage of revenue.',
        f'''SELECT currency,sum(fixed_cost) AS fixed_cost,sum(variable_cost) AS variable_cost,
        sum(fixed_cost)*100/nullif(greatest(sum(revenue),0),0) AS fixed_cost_pct,
        sum(variable_cost)*100/nullif(greatest(sum(revenue),0),0) AS variable_cost_pct
        FROM analytics.nl_practice_daily WHERE {WINDOW} GROUP BY currency ORDER BY currency''',
        ('currency','fixed_cost','variable_cost','fixed_cost_pct','variable_cost_pct')),
    Query('volatility','Population coefficient of variation for observed weekly revenue and expense; at least two observed weeks required.',
        f'''WITH weeks AS (SELECT week_start,currency,sum(revenue) AS revenue,sum(expense) AS expense,
        (make_date(year,month,1)>=%(start)s AND (make_date(year,month,1)+interval '1 month'-interval '1 day')::date<=%(end)s) AS selected_full_month
        FROM analytics.nl_practice_daily WHERE {WINDOW} GROUP BY week_start,currency)
        SELECT currency,count(*) AS observed_weeks,
        CASE WHEN count(*)>=2 THEN stddev_pop(revenue)/nullif(abs(avg(revenue)),0) END AS revenue_cv,
        CASE WHEN count(*)>=2 THEN stddev_pop(expense)/nullif(abs(avg(expense)),0) END AS expense_cv
        FROM weeks GROUP BY currency ORDER BY currency''',
        ('currency','observed_weeks','revenue_cv','expense_cv')),
    Query('providers','All internal provider identifiers with observed attributed revenue minus recorded attributed cost. NOT fully loaded contribution; cost completeness is unverified. NULL provider identifies unattributed practice activity.',
        f'''SELECT provider_key,currency,sum(revenue) AS revenue,sum(expense) AS recorded_cost,
        sum(revenue)-sum(expense) AS observed_net
        FROM analytics.nl_provider_daily WHERE {WINDOW} GROUP BY provider_key,currency ORDER BY provider_key NULLS LAST,currency''',
        ('provider_key','currency','revenue','recorded_cost','observed_net'),True),
)}
LABELS={'revenue':'Recorded revenue','expense':'Recorded expenses','net':'Recorded net','margin_pct':'Net margin (%)',
 'revenue_growth_pct':'Revenue growth (%)','fixed_cost':'Fixed costs','variable_cost':'Variable costs',
 'fixed_cost_pct':'Fixed costs / revenue (%)','variable_cost_pct':'Variable costs / revenue (%)',
 'observed_weeks':'Observed weeks','revenue_cv':'Revenue coefficient of variation','expense_cv':'Expense coefficient of variation',
 'recorded_cost':'Recorded attributed costs','observed_net':'Observed attributed net (cost completeness unverified)'}

class Unreliable(ValueError): pass

def allowed_catalog(provider_access):
    return [q for q in CATALOG.values() if provider_access or not q.provider_access]

def validate_sql(key,sql,parameters,start,end,provider_access):
    check_range(start,end)
    query=CATALOG.get(key)
    if not query or (query.provider_access and not provider_access): raise Unreliable('Query is outside the permitted scope')
    # A deliberately strict allowlist of full statements, tables, columns and functions.
    # Even equivalent unreviewed SQL is refused. Execute query.sql, never this untrusted string.
    if sql.strip()!=query.sql: raise Unreliable('SQL is not a reviewed statement')
    if parameters!={'start':start.isoformat(),'end':end.isoformat()}:
        raise Unreliable('Date parameters differ from the explicitly selected period')
    return query,{'start':start,'end':end}

def validate_result(query,rows):
    if len(rows)>100: raise Unreliable('Result exceeds the supported row limit; choose a shorter period')
    for row in rows:
        if set(row)!=set(query.columns): raise Unreliable('Unexpected result columns')
    currencies={row['currency'] for row in rows}
    if currencies and (None in currencies or len(currencies)!=1):
        raise Unreliable('Currency metadata is missing or mixed')

def render_explanation(selections,query,rows):
    """The model selects facts; only returned cells supply numbers or identity values."""
    if not rows: return 'No recorded data was returned for the selected dates.'
    if not selections: raise Unreliable('No grounded explanation was provided')
    lines=[]
    for fact in selections:
        index=fact['row']; column=fact['column']
        if type(index) is not int or not 0<=index<len(rows) or column not in query.columns or column not in LABELS:
            raise Unreliable('Explanation references an invalid result cell')
        row=rows[index];value=row[column]
        context=[]
        for key in ('year','month','week_start','provider_key'):
            if key in row: context.append(key.replace('_',' ')+': '+str(row[key] if row[key] is not None else 'unattributed'))
        prefix=('; '.join(context)+'. ') if context else ''
        text='undefined from the available data' if value is None else str(value)
        if value is not None and 'pct' in column:
            with localcontext() as ctx:
                ctx.prec=60
                text=format(Decimal(str(value)).quantize(Decimal('.01')), 'f')
        suffix=(' '+row['currency']) if column in {'revenue','expense','net','fixed_cost','variable_cost','recorded_cost','observed_net'} and value is not None else ''
        lines.append(prefix+LABELS[column]+' is '+text+suffix+'.')
    return '\n'.join(lines)
