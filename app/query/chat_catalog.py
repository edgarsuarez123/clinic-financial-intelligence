"""Only these reviewed aggregate statements can be selected by a conversation."""
from .catalog import Query, TOTALS

WHERE="full_date BETWEEN %(start)s AND %(end)s AND (%(clinic_location)s::text IS NULL OR clinic_location=%(clinic_location)s)"
CHAT_CATALOG={q.key:q for q in (
    Query('cost_breakdown','Recorded fixed and variable costs and each as a percentage of revenue.',
        f'''SELECT currency,sum(fixed_cost) AS fixed_cost,sum(variable_cost) AS variable_cost,
            sum(fixed_cost)*100/nullif(greatest(sum(revenue),0),0) AS fixed_cost_pct,
            sum(variable_cost)*100/nullif(greatest(sum(revenue),0),0) AS variable_cost_pct
            FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY currency ORDER BY currency''',
        ('currency','fixed_cost','variable_cost','fixed_cost_pct','variable_cost_pct')),
    Query('volatility','Population coefficient of variation for observed weekly revenue and expenses; at least two observed weeks.',
        f'''WITH weeks AS (SELECT date_trunc('week',full_date)::date AS week_start,currency,sum(revenue) AS revenue,sum(expense) AS expense
            FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY week_start,currency)
            SELECT currency,count(*) AS observed_weeks,
            CASE WHEN count(*)>=2 THEN stddev_pop(revenue)/nullif(abs(avg(revenue)),0) END AS revenue_cv,
            CASE WHEN count(*)>=2 THEN stddev_pop(expense)/nullif(abs(avg(expense)),0) END AS expense_cv
            FROM weeks GROUP BY currency ORDER BY currency''',('currency','observed_weeks','revenue_cv','expense_cv')),
    Query('providers','Observed provider revenue minus recorded attributed cost, not verified fully loaded contribution.',
        f'''SELECT provider_key,currency,sum(revenue) AS revenue,sum(expense) AS recorded_cost,sum(revenue)-sum(expense) AS observed_net
            FROM analytics.nl_provider_location_daily WHERE {WHERE} GROUP BY provider_key,currency ORDER BY provider_key NULLS LAST,currency''',
        ('provider_key','currency','revenue','recorded_cost','observed_net'),True),
    Query('summary','Revenue, expenses, net and margin for the selected clinic and dates.',
        f'SELECT currency,{TOTALS} FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY currency ORDER BY currency',
        ('currency','revenue','expense','net','margin_pct')),
    *[Query(key,desc,f"SELECT date_trunc('{unit}',full_date)::date AS period,currency,{TOTALS} FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY period,currency ORDER BY period,currency",
        ('period','currency','revenue','expense','net','margin_pct')) for key,unit,desc in [
            ('monthly','month','Monthly revenue, expenses, net and margin.'),
            ('weekly','week','Monday–Sunday seven-day weekly revenue, expenses, net and margin.'),
            ('quarterly','quarter','Calendar-quarter revenue, expenses, net and margin.')]],
    Query('insurance','Total recorded revenue grouped by medical insurance.',
        f'SELECT medical_insurance,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY medical_insurance,currency ORDER BY revenue DESC',
        ('medical_insurance','currency','revenue')),
    Query('billing_codes','Total recorded revenue grouped by billing code.',
        f'SELECT billing_code,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY billing_code,currency ORDER BY revenue DESC',
        ('billing_code','currency','revenue')),
    Query('insurance_codes','Total recorded revenue by medical insurance and billing code.',
        f'SELECT medical_insurance,billing_code,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY medical_insurance,billing_code,currency ORDER BY medical_insurance,billing_code',
        ('medical_insurance','billing_code','currency','revenue')),
    Query('locations','Recorded revenue, expenses and net by clinic location.',
        f'SELECT clinic_location,currency,{TOTALS} FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY clinic_location,currency ORDER BY clinic_location,currency',
        ('clinic_location','currency','revenue','expense','net','margin_pct')),
    Query('monthly_insurance','Monthly recorded revenue grouped by medical insurance payer over time.',
        f"SELECT date_trunc('month',full_date)::date AS period,medical_insurance,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY period,medical_insurance,currency ORDER BY period,medical_insurance,currency",
        ('period','medical_insurance','currency','revenue')),
    Query('monthly_billing_codes','Monthly recorded revenue grouped by billing code over time.',
        f"SELECT date_trunc('month',full_date)::date AS period,billing_code,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY period,billing_code,currency ORDER BY period,billing_code,currency",
        ('period','billing_code','currency','revenue')),
    Query('quarterly_insurance','Quarterly recorded revenue grouped by medical insurance payer.',
        f"SELECT date_trunc('quarter',full_date)::date AS period,medical_insurance,currency,sum(revenue) AS revenue FROM analytics.nl_insurance_daily WHERE {WHERE} GROUP BY period,medical_insurance,currency ORDER BY period,medical_insurance,currency",
        ('period','medical_insurance','currency','revenue')),
    Query('monthly_locations','Monthly revenue, expenses and net by clinic location over time.',
        f"SELECT date_trunc('month',full_date)::date AS period,clinic_location,currency,{TOTALS} FROM analytics.nl_location_daily WHERE {WHERE} GROUP BY period,clinic_location,currency ORDER BY period,clinic_location,currency",
        ('period','clinic_location','currency','revenue','expense','net','margin_pct')),
    Query('provider_monthly','Monthly revenue and recorded cost by provider over time.',
        f"SELECT date_trunc('month',full_date)::date AS period,provider_key,currency,sum(revenue) AS revenue,sum(expense) AS recorded_cost,sum(revenue)-sum(expense) AS observed_net FROM analytics.nl_provider_location_daily WHERE {WHERE} GROUP BY period,provider_key,currency ORDER BY period,provider_key,currency",
        ('period','provider_key','currency','revenue','recorded_cost','observed_net'),True),
)}
