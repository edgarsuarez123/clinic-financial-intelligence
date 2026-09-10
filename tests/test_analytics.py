from datetime import date,timedelta
from decimal import Decimal,localcontext
import pytest
from app.analytics.calculations import (Transaction,CostCoverage,analytics,period_series,
    provider_contributions,summarize,coefficient_of_variation,growth)

D=Decimal
START=date(2026,1,5); END=date(2026,2,15)

def test_week_includes_both_weekend_days():
    rows=[Transaction(date(2026,1,day),D('10'),'revenue','r','revenue') for day in range(5,12)]
    report=analytics(rows,date(2026,1,5),date(2026,1,11))
    assert len(report['weekly'])==1
    assert report['weekly'][0]['revenue']==D('70')
    assert report['weekly'][0]['period_end']==date(2026,1,11)

def tx(day,amount,kind='revenue',category=None,provider=None):
    category=category or ('revenue' if kind=='revenue' else 'fixed_cost')
    return Transaction(day,D(amount),kind,category,category,provider)

@pytest.fixture
def six_weeks():
    rows=[]
    for i,(rev,expense) in enumerate(zip(('100','200','300','400','500','600'),('40','60','90','110','130','150'))):
        provider='A' if i in (0,1,3) else 'B'
        rows.append(tx(START+timedelta(weeks=i),rev,provider=provider))
        rows.append(tx(START+timedelta(weeks=i),expense,'expense',
                       'fixed_cost' if i in (0,3,5) else 'variable_cost',
                       None if i in (2,5) else provider))
    return rows

def test_weekly_totals_margins_and_cost_breakdown(six_weeks):
    result=analytics(six_weeks,START,END)
    assert len(result['weekly'])==6
    summary=result['summary']
    assert summary['revenue']==D('2100')
    assert summary['expense']==D('580')
    assert summary['net']==D('1520')
    assert summary['fixed_cost']==D('300')
    assert summary['variable_cost']==D('280')
    assert result['weekly'][0]['margin_pct']==D('60')
    assert abs(summary['margin_pct']-D('72.38095238095238095238'))<D('1e-18')

def test_four_and_twelve_week_averages_use_available_history(six_weeks):
    weeks=analytics(six_weeks,START,END)['weekly']
    assert weeks[3]['revenue_ma_4']['value']==D('250')
    assert weeks[-1]['revenue_ma_4']['value']==D('450')
    assert weeks[-1]['expense_ma_4']['value']==D('120')
    assert weeks[-1]['revenue_ma_12']['value']==D('350')
    assert weeks[-1]['revenue_ma_12']['observed_periods']==6
    assert not weeks[-1]['revenue_ma_12']['complete_window']
    assert weeks[3]['revenue_ma_4']['complete_window']

def test_week_over_week_growth(six_weeks):
    weeks=analytics(six_weeks,START,END)['weekly']
    assert weeks[0]['revenue_growth_pct'] is None
    assert weeks[1]['revenue_growth_pct']==D('100')
    assert weeks[1]['expense_growth_pct']==D('50')

def test_monthly_totals_and_growth(six_weeks):
    months=analytics(six_weeks,date(2026,1,1),date(2026,2,28))['monthly']
    assert [x['revenue'] for x in months]==[D('1000'),D('1100')]
    assert [x['expense'] for x in months]==[D('300'),D('280')]
    assert months[1]['revenue_growth_pct']==D('10')

def test_category_percentages_and_history(six_weeks):
    result=analytics(six_weeks,START,END)
    cats={r['category_key']:r for r in result['summary']['categories']}
    assert cats['fixed_cost']['amount']==D('300')
    assert abs(cats['variable_cost']['pct_revenue']-D('13.33333333333333333333'))<D('1e-18')
    assert result['weekly'][0]['categories'][0]['pct_revenue']==D('40')

def test_missing_periods_are_not_imputed_or_compared():
    rows=[tx(START,'100'),tx(START+timedelta(weeks=2),'300')]
    weeks=analytics(rows,START,START+timedelta(days=20))['weekly']
    assert weeks[1]['revenue'] is None and not weeks[1]['observed']
    assert weeks[2]['revenue_growth_pct'] is None
    assert weeks[2]['revenue_ma_4']['value']==D('200')
    assert weeks[2]['revenue_ma_4']['observed_periods']==2

def test_partial_periods_do_not_generate_misleading_growth(six_weeks):
    result=analytics(six_weeks,START+timedelta(days=1),END)
    assert result['weekly'][0]['partial']
    assert result['weekly'][1]['revenue_growth_pct'] is None
    assert result['monthly'][1]['revenue_growth_pct'] is None

def test_zero_revenue_and_negative_margin():
    result=analytics([tx(START,'50','expense')],START,START+timedelta(days=6))
    assert result['summary']['revenue']==D('0')
    assert result['summary']['net']==D('-50')
    assert result['summary']['margin_pct'] is None
    assert result['summary']['categories'][0]['pct_revenue'] is None
    loss=summarize([tx(START,'100'),tx(START,'150','expense')])
    assert loss['margin_pct']==D('-50')

def test_empty_dataset_degrades_to_unknown():
    result=analytics([],START,END)
    assert result['summary']['revenue'] is None
    assert all(not r['observed'] for r in result['weekly'])
    assert result['volatility']['revenue']['value'] is None

def test_single_week_cv_unavailable():
    result=analytics([tx(START,'100')],START,START+timedelta(days=6))
    assert result['volatility']['revenue']['reason']=='fewer_than_two_periods'
    assert result['weekly'][0]['revenue_ma_4']['value']==D('100')

def test_population_cv_worked_example():
    # [100,300]: mean 200, population variance 10000, stddev 100, CV 0.5.
    assert coefficient_of_variation([D('100'),D('300')])['value']==D('.5')
    assert coefficient_of_variation([D('0'),D('0')])['reason']=='zero_mean'
    assert coefficient_of_variation([D('-100'),D('-300')])['value']==D('.5')

@pytest.mark.parametrize('previous',[None,D('0'),D('-10')])
def test_nonpositive_growth_denominator(previous):
    assert growth(D('10'),previous) is None

def test_provider_cost_confirmation_and_no_automatic_allocation(six_weeks):
    coverage={'A':CostCoverage(START,END,'Synthetic confirmed salary, benefits and allocated costs.')}
    result=provider_contributions(six_weeks,START,END,coverage)
    a,b=result['providers']
    assert a['provider_key']=='A' and a['revenue']==D('700')
    assert a['fully_loaded_cost']==D('210') and a['contribution']==D('490')
    assert a['contribution_margin_pct']==D('70')
    assert b['attributed_expense']==D('130') and b['fully_loaded_cost'] is None
    assert b['contribution'] is None
    assert result['unattributed']['expense']==D('240')

def test_cost_confirmation_does_not_extend_beyond_approved_dates(six_weeks):
    result=provider_contributions(six_weeks,START,END,{'A':CostCoverage(START,END-timedelta(days=1),'Only a shorter period.')})
    assert result['providers'][0]['contribution'] is None

def test_provider_attribution_missing():
    result=provider_contributions([tx(START,'100')],START,END,{})
    assert result['providers']==[]
    assert result['unattributed']['revenue']==D('100')

def test_refunds_and_decimal_accuracy():
    result=summarize([tx(START,'.10'),tx(START,'.20'),tx(START,'-.10','expense')])
    assert result['revenue']==D('.30') and result['net']==D('.40')

def test_results_do_not_depend_on_callers_decimal_context(six_weeks):
    expected=analytics(six_weeks,START,END)
    with localcontext() as ctx:
        ctx.prec=6
        assert analytics(six_weeks,START,END)==expected

@pytest.mark.parametrize('amount',[0.1,D('NaN'),D('Infinity'),D('.001')])
def test_invalid_money_rejected(amount):
    with pytest.raises(ValueError): Transaction(START,amount,'revenue','revenue','revenue')

def test_year_and_leap_boundaries():
    rows=[tx(date(2021,1,1),'100')]
    weeks=period_series(rows,date(2020,12,28),date(2021,1,3),'week')
    assert len(weeks)==1 and weeks[0]['period_start']==date(2020,12,28)
    months=period_series([tx(date(2024,2,29),'1')],date(2024,2,1),date(2024,3,31),'month')
    assert months[0]['period_end']==date(2024,2,29)
    assert months[1]['revenue'] is None

def test_invalid_ranges_rejected():
    with pytest.raises(ValueError): analytics([],END,START)
    with pytest.raises(ValueError): analytics([],date(2000,1,1),date(2020,1,1))

def test_fact_classification_must_match():
    with pytest.raises(ValueError): Transaction(START,D('10'),'expense','wrong','revenue')
