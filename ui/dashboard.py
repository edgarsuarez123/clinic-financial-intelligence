"""Temporary analytics demo UI. All business results come from the REST API."""
from datetime import date
from decimal import Decimal, Context, localcontext, ROUND_HALF_UP
import altair as alt
import streamlit as st


def money(value,currency=''):
    if value is None: return '—'
    with localcontext(Context(prec=50)):
        return (currency+' ' if currency else '')+format(Decimal(value),',.2f')

def percent(value):
    return '—' if value is None else format(Decimal(value),'.2f')+'%'

def chart_cents(value):
    if value is None: return None
    with localcontext(Context(prec=50)):
        cents=int(Decimal(value).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)*100)
    if abs(cents)>9007199254740991:
        raise ValueError('Amount exceeds exact browser chart range')
    return cents

def trend_rows(periods,fields):
    data=[]
    for field,label in fields:
        segment=0
        for period in periods:
            value=period[field]
            if isinstance(value,dict): value=value['value']
            if value is None:
                segment+=1
                continue
            data.append({'period':period['period_start'],'series':label,'cents':chart_cents(value),
                         'amount':money(value),'segment':label+str(segment)})
    return data

def draw_trend(periods,fields,currency):
    try: rows=trend_rows(periods,fields)
    except ValueError:
        st.info('These amounts exceed the chart display range. Exact values are shown in the table below.')
        return
    if not rows: return
    chart=alt.Chart(alt.Data(values=rows)).mark_line(point=True).encode(
        x=alt.X('period:T',title='Period start'),
        y=alt.Y('cents:Q',title=currency or 'Amount',axis=alt.Axis(labelExpr="format(datum.value / 100, ',.0f')")),
        color=alt.Color('series:N',title=None),detail='segment:N',
        tooltip=[alt.Tooltip('period:T',title='Period start'),alt.Tooltip('series:N',title='Series'),
                 alt.Tooltip('amount:N',title='Amount')]).properties(height=280)
    st.altair_chart(chart,width='stretch')

def render_periods(periods,currency,weekly):
    draw_trend(periods,[('revenue','Revenue'),('expense','Expense'),('net','Net')],currency)
    st.dataframe([{'Period':r['period_start'],'Coverage':'Selected partial period' if r['partial'] else 'Full calendar window',
        'Data':'Observed' if r['observed'] else 'No data','Revenue':money(r['revenue'],currency),
        'Expense':money(r['expense'],currency),'Net':money(r['net'],currency),'Margin':percent(r['margin_pct']),
        'Revenue growth':percent(r['revenue_growth_pct']),'Expense growth':percent(r['expense_growth_pct'])}
        for r in periods],hide_index=True,width='stretch')
    if weekly:
        st.subheader('4-week and 12-week moving averages')
        draw_trend(periods,[('revenue_ma_4','Revenue · 4 weeks'),('revenue_ma_12','Revenue · 12 weeks'),
                            ('expense_ma_4','Expense · 4 weeks'),('expense_ma_12','Expense · 12 weeks')],currency)
        st.caption('Averages use observed values within each trailing calendar window. Short or incomplete windows are labeled below.')
        st.dataframe([{'Week':r['period_start'],'Revenue 4-week':money(r['revenue_ma_4']['value'],currency),
            'Revenue 12-week':money(r['revenue_ma_12']['value'],currency),
            'Expense 4-week':money(r['expense_ma_4']['value'],currency),
            'Expense 12-week':money(r['expense_ma_12']['value'],currency),
            '4-week observations':r['revenue_ma_4']['observed_periods'],
            '12-week observations':r['revenue_ma_12']['observed_periods'],
            '4-week complete':r['revenue_ma_4']['complete_window'],
            '12-week complete':r['revenue_ma_12']['complete_window']} for r in periods],hide_index=True,width='stretch')


def render_dashboard(call,message,token):
    st.header('Practice financial overview')
    status,permissions=call('GET','/api/v1/analytics/config',token)
    if status!=200: message(permissions); return
    if not permissions['enabled']:
        st.info('Analytics access is not configured for this account. Ask your administrator to approve dashboard access.')
        return
    if permissions.get('synthetic_data'):
        st.warning('Synthetic demonstration data. These results do not describe a real clinic.')
    status,metadata=call('GET','/api/v1/analytics/metadata',token)
    if status!=200: message(metadata); return
    if not metadata['row_count']:
        st.info('No completed financial imports yet. Use Imports to load an approved export.')
        return
    first=date.fromisoformat(metadata['first_date']); last=date.fromisoformat(metadata['last_date'])
    with st.form('analytics_dates'):
        left,right=st.columns(2)
        start=left.date_input('From',value=first)
        end=right.date_input('Through',value=last)
        st.form_submit_button('Update analytics')
    if end<start:
        st.error('The end date must be on or after the start date.'); return
    params={'start':start.isoformat(),'end':end.isoformat()}
    with st.spinner('Loading analytics…'):
        status,result=call('GET','/api/v1/analytics/dashboard',token,params=params)
    if status!=200: message(result); return
    summary=result['summary']; currency=result['currency'] or ''
    st.caption('Based on imported records for the selected dates. Missing periods are not treated as zero activity.')
    if not summary['observed']:
        st.info('No financial records in this date range.'); return
    cards=st.columns(4)
    for card,label,value in zip(cards,['Revenue','Expense','Net','Net margin'],
                               [money(summary['revenue'],currency),money(summary['expense'],currency),money(summary['net'],currency),percent(summary['margin_pct'])]):
        card.metric(label,value)
    weekly,monthly=st.tabs(['Weekly','Monthly'])
    with weekly: render_periods(result['weekly'],currency,True)
    with monthly: render_periods(result['monthly'],currency,False)
    st.subheader('Expense mix')
    fixed,variable=st.columns(2)
    fixed.metric('Fixed costs',money(summary['fixed_cost'],currency))
    variable.metric('Variable costs',money(summary['variable_cost'],currency))
    labels=result['category_labels']
    st.dataframe([{'Category':labels.get(r['category_key'],'Expense category'),'Amount':money(r['amount'],currency),
                   '% of revenue':percent(r['pct_revenue'])} for r in summary['categories']],hide_index=True,width='stretch')
    with st.expander('Expense categories over time'):
        frequency=st.radio('Reporting period',['Monthly','Weekly'],horizontal=True)
        history=result['monthly'] if frequency=='Monthly' else result['weekly']
        st.dataframe([{'Period':period['period_start'],'Category':labels.get(r['category_key'],'Expense category'),
            'Amount':money(r['amount'],currency),'% of revenue':percent(r['pct_revenue'])}
            for period in history for r in period['categories']],hide_index=True,width='stretch')
    st.subheader('Revenue and expense volatility')
    volatility=result['volatility']
    left,right=st.columns(2)
    for card,field in ((left,'revenue'),(right,'expense')):
        item=volatility[field]
        card.metric(field.title()+' CV','—' if item['value'] is None else format(Decimal(item['value']),'.4f'))
        card.caption(f"{item['samples']} eligible weeks. " + ({'fewer_than_two_periods':'At least two observed, untrimmed weeks are required.',
                'zero_mean':'Undefined because the mean is zero.'}.get(item['reason'],'')))
    st.caption('CV is a unitless ratio. '+volatility['basis'])
    st.caption(f"{volatility['missing_weeks']} weeks have no data; {volatility['partial_weeks']} weeks are trimmed by the selected dates.")
    if permissions.get('provider_access'):
        if st.checkbox('Show provider profitability'):
            status,providers=call('GET','/api/v1/analytics/providers',token,params=params)
            if status!=200: message(providers)
            elif not providers['providers']: st.info('No provider-attributed records in this range.')
            else:
                st.subheader('Provider profitability')
                st.dataframe([{'Provider':r['label'],'Attributed revenue':money(r['revenue'],currency),
                    'Observed attributed expense':money(r['attributed_expense'],currency),
                    'Confirmed fully loaded cost':money(r['fully_loaded_cost'],currency),
                    'Contribution':money(r['contribution'],currency),'Contribution margin':percent(r['contribution_margin_pct']),
                    'Cost status':'Confirmed for selected dates' if r['cost_complete'] else 'Not confirmed',
                    'Cost basis':r['cost_basis'] or 'No complete cost basis configured'} for r in providers['providers']],
                    hide_index=True,width='stretch')
                for note in providers['notes']: st.caption(note)
                unattributed=providers['unattributed']
                st.write('Unattributed revenue: '+money(unattributed['revenue'],currency)+
                         ' · Unattributed expense: '+money(unattributed['expense'],currency))
    else:
        st.caption('Provider costs and contribution margins require separate access.')
    with st.expander('Calculation definitions and data limits'):
        for note in result['data_notes']: st.write(note)
