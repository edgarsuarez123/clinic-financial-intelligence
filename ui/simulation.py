"""Temporary demo UI; calculations and authorization remain in the API."""
import json
from uuid import uuid4
import altair as alt
from datetime import date
from pathlib import Path
import streamlit as st
import pandas as pd
from dashboard import money,draw_trend,chart_cents

def render_simulation(call,message,token):
    st.header('Staffing & clinic budget')
    st.caption('Model current or new clinic costs, employee groups and hiring decisions. Enter zero explicitly for costs that do not apply.')
    status,options=call('GET','/api/v1/simulations/config',token)
    if status!=200: message(options); return
    if not options['enabled']:
        st.info('Simulation access requires administrator configuration.'); return
    current=st.session_state.get('budget_document')
    if current:
        status,checked=call('GET','/api/v1/simulations/budgets/'+current['budget_id'],token)
        if status!=200:
            for key in ('budget_document','budget_example','budget_result','budget_name'): st.session_state.pop(key,None)
            st.session_state.budget_generation=st.session_state.get('budget_generation',0)+1
            message(checked); return
    if options['synthetic_data']: st.warning('Synthetic demo only. Do not enter real clinic or patient data.')
    st.caption('Payroll taxes are your effective employer percentage of base salary. Rates, caps and jurisdiction rules are not supplied by this app. All employee amounts are per person.')
    st.caption('Save & calculate stores this budget in the database. Saved budgets survive sign-out and restarts. Unsaved edits are not retained. Budgets are private to your account.')
    offset=st.session_state.get('budget_offset',0)
    status,listing=call('GET','/api/v1/simulations/budgets',token,params={'offset':offset})
    if status!=200: message(listing); return
    choices={item['budget_id']:item for item in listing['budgets']}
    selected=st.selectbox('Saved budgets',list(choices),index=None,
        format_func=lambda key:choices[key]['name']+' · revision '+str(choices[key]['revision']))
    left,right=st.columns(2)
    if left.button('Previous saved budgets',disabled=offset==0):
        st.session_state.budget_offset=max(0,offset-50); st.rerun()
    if right.button('Next saved budgets',disabled=not listing['has_more']):
        st.session_state.budget_offset=offset+50; st.rerun()
    if st.button('Open saved budget',disabled=selected is None):
        status,doc=call('GET','/api/v1/simulations/budgets/'+selected,token)
        if status==200: load_document(doc); st.rerun()
        else: message(doc)
    if st.button('New blank budget'):
        for key in ('budget_example','budget_document','budget_result','budget_name','budget_pending_create'):
            st.session_state.pop(key,None)
        st.session_state.budget_generation=st.session_state.get('budget_generation',0)+1
        st.rerun()
    comparison=st.multiselect('Saved budgets to compare (up to four)',list(choices),max_selections=4,
        format_func=lambda key:choices[key]['name']+' · revision '+str(choices[key]['revision']))
    if st.button('Compare saved budgets',disabled=len(comparison)<2):
        docs=[]
        for key in comparison:
            status,doc=call('GET','/api/v1/simulations/budgets/'+key,token)
            if status!=200: message(doc); break
            docs.append(doc)
        else: st.session_state.budget_comparison=docs
    if st.session_state.get('budget_comparison'):
        # Re-authorize and refresh every displayed snapshot; revoked history permissions must hide it.
        docs=[]
        for old in st.session_state.budget_comparison:
            status,doc=call('GET','/api/v1/simulations/budgets/'+old['budget_id'],token)
            if status!=200:
                st.session_state.pop('budget_comparison',None); message(doc); break
            docs.append(doc)
        else: render_comparison(docs)
    if st.button('Load explicitly synthetic example'):
        st.session_state.budget_example=json.loads((Path(__file__).resolve().parents[1]/'config/simulation-example.json').read_text())
        for key in ('budget_document','budget_result','budget_pending_create'): st.session_state.pop(key,None)
        st.session_state.budget_name='Synthetic clinic example'
        st.session_state.budget_generation=st.session_state.get('budget_generation',0)+1
        st.rerun()
    seed=st.session_state.get('budget_example',{})
    generation=st.session_state.get('budget_generation',0)
    if st.session_state.get('budget_saved_notice'):
        st.success(st.session_state.pop('budget_saved_notice'))
    current=st.session_state.get('budget_document')
    if current:
        st.caption('Editing '+current['name']+' · revision '+str(current['revision'])+' · saved '+current['updated_at'])
    with st.form('budget_'+str(generation)):
        budget_name=st.text_input('Budget name',value=st.session_state.get('budget_name',''),max_chars=100)
        cols=st.columns(3)
        start=cols[0].date_input('Plan start date',value=date.fromisoformat(seed['start_date']) if seed else None)
        horizon=cols[1].text_input('Months to model',value=str(seed.get('months','')))
        currency=cols[2].text_input('Currency (three-letter code)',value=seed.get('currency',''))
        existing=st.text_input('Existing monthly clinic revenue',value=seed.get('existing_monthly_revenue',''))
        basis=st.text_input('Existing revenue basis (enter zero revenue for a new clinic)',value=seed.get('existing_revenue_basis',''))
        st.subheader('Employees')
        st.caption('Add one row per group with the same pay and tax assumptions. Set start/end months to schedule hires or departures. Existing staff: included_in_clinic_baseline, with monthly revenue 0. New contribution: incremental. Cost-only: none.')
        fields=['role_type','headcount','start_month','end_month','revenue_mode','annual_salary','benefits_pct','payroll_tax_pct','annual_malpractice','annual_other_fixed_cost','onboarding_cost','variable_cost_pct','cost_basis','monthly_revenue','revenue_basis','historical_provider_ids','historical_start','historical_end']
        rows=[]
        for s in seed.get('staff',[]):
            rows.append({k:str(s.get(k,'')) for k in fields}|{'monthly_revenue':s['revenue'].get('monthly_revenue',''),'revenue_basis':s['revenue']['basis'],'historical_provider_ids':','.join(s['revenue'].get('provider_keys',[])), 'historical_start':s['revenue'].get('start') or '', 'historical_end':s['revenue'].get('end') or ''})
        staff=st.data_editor(pd.DataFrame(rows,columns=fields,dtype='string'),num_rows='dynamic',key='staff_'+str(generation),column_config={k:st.column_config.TextColumn(k) for k in fields},width='stretch')
        st.caption('For a historical per-provider baseline, leave monthly_revenue blank and enter comma-separated provider UUIDs plus YYYY-MM-DD historical dates. Provider access is required. Applying that mean to a hire remains an assumption.')
        st.subheader('Clinic costs')
        st.caption('Add rent, utilities, software, insurance or any other expense. Monthly amounts recur over the specified months; one-time amounts occur only in the start month. Do not repeat payroll costs here.')
        costs=st.data_editor(pd.DataFrame([{k:str(v) for k,v in c.items()} for c in seed.get('clinic_costs',[])],columns=['label','monthly_amount','one_time_amount','start_month','end_month'],dtype='string'),num_rows='dynamic',key='costs_'+str(generation),column_config={k:st.column_config.TextColumn(k) for k in ['label','monthly_amount','one_time_amount','start_month','end_month']},width='stretch')
        st.subheader('Sensitivity assumptions')
        scenarios=[]
        for i,name in enumerate(['pessimistic','expected','optimistic']):
            s=next((x for x in seed.get('scenarios',[]) if x['name']==name),{})
            st.write(name.title())
            cols=st.columns(3)
            rev=cols[0].text_input('Revenue multiplier',value=s.get('revenue_multiplier',''),key=name+'rev'+str(generation))
            cost=cols[1].text_input('Recurring cost multiplier',value=s.get('fixed_cost_multiplier',''),key=name+'cost'+str(generation))
            ramp=cols[2].text_input('Ramp month:productivity, comma-separated',value=','.join(str(x['month'])+':'+x['productivity'] for x in s.get('ramp',[])),placeholder='1:0.5,4:1',key=name+'ramp'+str(generation))
            ramp_basis=st.text_input('Ramp assumption basis',value=s.get('ramp_basis',''),key=name+'basis'+str(generation))
            scenarios.append((name,rev,cost,ramp,ramp_basis))
        submit=st.form_submit_button('Save & calculate')
        duplicate=st.form_submit_button('Save as new budget')
    if submit or duplicate:
        st.session_state.pop('budget_result',None)
        try:
            def records(value):
                if isinstance(value,pd.DataFrame): return value.fillna('').to_dict('records')
                if isinstance(value,dict): return [dict(zip(value,items)) for items in zip(*value.values())]
                return value
            staff_inputs=[]
            for row in records(staff):
                s={k:row[k] for k in fields[:13]}
                for k in ('headcount','start_month','end_month'): s[k]=int(s[k])
                ids=str(row.get('historical_provider_ids') or '').strip()
                s['revenue']={'kind':'historical','provider_keys':[x.strip() for x in ids.split(',')],'start':row['historical_start'],'end':row['historical_end'],'basis':row['revenue_basis']} if ids else {'kind':'manual','monthly_revenue':row['monthly_revenue'],'basis':row['revenue_basis']}
                staff_inputs.append(s)
            cost_inputs=[dict(c,start_month=int(c['start_month']),end_month=int(c['end_month'])) for c in records(costs)]
            payload={'start_date':start.isoformat(),'months':int(horizon),'currency':currency,'existing_monthly_revenue':existing,'existing_revenue_basis':basis,'staff':staff_inputs,'clinic_costs':cost_inputs,'scenarios':[{'name':n,'revenue_multiplier':r,'fixed_cost_multiplier':c,'ramp':[{'month':int(pair.split(':')[0]),'productivity':pair.split(':')[1]} for pair in ramp.split(',')],'ramp_basis':b} for n,r,c,ramp,b in scenarios]}
            request_body={'name':budget_name,'plan':payload}
            with st.spinner('Saving budget and calculating three scenarios…'):
                if current and not duplicate:
                    request_body['expected_revision']=current['revision']
                    status,result=call('PUT','/api/v1/simulations/budgets/'+current['budget_id'],token,json=request_body)
                else:
                    signature=json.dumps(request_body,sort_keys=True)
                    pending=st.session_state.get('budget_pending_create')
                    if not pending or pending['signature']!=signature:
                        pending={'signature':signature,'budget_id':str(uuid4())}
                        st.session_state.budget_pending_create=pending
                    request_body['budget_id']=pending['budget_id']
                    status,result=call('POST','/api/v1/simulations/budgets',token,json=request_body)
            if status==200:
                load_document(result)
                st.session_state.pop('budget_pending_create',None)
                st.session_state.budget_saved_notice='Budget saved. You can reopen it after signing in again.'
                st.rerun()
            else: message(result)
        except (ValueError,TypeError,KeyError,IndexError,AttributeError):
            st.error('Complete every required field. Counts and months must be integers; ramps use month:productivity pairs.')
    result=st.session_state.get('budget_result')
    if not result: return
    # Refresh permission checks before displaying sensitive saved results on reruns.
    current=st.session_state.get('budget_document')
    if current:
        status,checked=call('GET','/api/v1/simulations/budgets/'+current['budget_id'],token)
        if status!=200:
            st.session_state.pop('budget_result',None); message(checked); return
    st.caption('Results are the last saved snapshot, not unsaved edits. Save & calculate refreshes historical inputs. Ramp curves are assumptions, not calibrated hiring estimates.')
    render_results(result)

def render_results(result):
    if result['ordering_note']: st.warning(result['ordering_note'])
    for tab,scenario in zip(st.tabs([x['scenario'].title() for x in result['scenarios']]),result['scenarios']):
        with tab:
            output,assumptions=st.columns([3,2])
            with assumptions:
                st.subheader('Full assumptions used')
                st.json(scenario['assumptions'],expanded=True)
            with output:
                ccy=scenario['assumptions']['plan']['currency']; summary=scenario['summary']
                st.metric('Projected cumulative net',money(summary['net'],ccy))
                first=summary['first_break_even']; sustained=summary['sustained_break_even_within_horizon']
                st.write('First cumulative break-even: '+('month '+str(first['month']) if first else 'not reached within horizon'))
                st.write('Sustained through modeled horizon: '+('from month '+str(sustained['month']) if sustained else 'not reached'))
                st.write('Break-even status: '+summary['break_even_status'])
                st.metric('Peak modeled upfront/closing deficit',money(summary['peak_modeled_deficit'],ccy))
                draw_trend([dict(x,period_start=x['start']) for x in scenario['periods']],[('revenue','Revenue'),('total_cost','Cost'),('net','Net')],ccy)
                draw_trend([dict(x,period_start=x['start']) for x in scenario['periods']],[('cumulative_revenue','Cumulative revenue'),('cumulative_cost','Cumulative cost'),('cumulative_net','Cumulative net')],ccy)
                draw_bars([(item['label'],item['amount']) for item in summary['cost_breakdown']],ccy,'Modeled cost breakdown')
                st.dataframe([{k:v for k,v in x.items() if k not in ('staff','clinic_costs')} for x in scenario['periods']],width='stretch')
                with st.expander('Employee payroll and clinic cost breakdown by month'):
                    st.write('Employee costs')
                    st.dataframe([dict(entry,month=p['month']) for p in scenario['periods'] for entry in p['staff']],width='stretch')
                    st.write('Clinic expenses')
                    st.dataframe([dict(entry,month=p['month']) for p in scenario['periods'] for entry in p['clinic_costs']],width='stretch')


def load_document(doc):
    st.session_state.budget_example=doc['plan']
    st.session_state.budget_document=doc
    st.session_state.budget_name=doc['name']
    st.session_state.budget_result=doc['result']
    st.session_state.budget_generation=st.session_state.get('budget_generation',0)+1


def draw_bars(items,currency,title):
    st.write(title)
    try: rows=[{'label':label,'cents':chart_cents(value),'amount':money(value,currency)} for label,value in items]
    except ValueError:
        st.info('Amounts exceed the exact browser chart range. Refer to the exact tables.'); return
    chart=alt.Chart(alt.Data(values=rows)).mark_bar().encode(
        y=alt.Y('label:N',title=None,sort=None,axis=alt.Axis(labelLimit=200)),
        x=alt.X('cents:Q',title=currency,axis=alt.Axis(labelExpr="format(datum.value / 100, ',.0f')")),
        color=alt.Color('label:N',legend=None),tooltip=['label:N','amount:N']).properties(height=max(240,len(rows)*25))
    st.altair_chart(chart,width='stretch')


def render_comparison(docs):
    st.subheader('Compare saved cost plans')
    st.caption('Expected scenario from each saved budget. Snapshots refresh when this page reruns; each tab shows the assumptions and saved revision.')
    expected=[next(s for s in doc['result']['scenarios'] if s['scenario']=='expected') for doc in docs]
    compatible=len({(d['plan']['currency'],d['plan']['start_date'],d['plan']['months']) for d in docs})==1
    if compatible:
        chart,assumptions=st.columns([3,2])
        with assumptions:
            st.write('Full assumptions for this comparison')
            for doc,s in zip(docs,expected):
                st.write(doc['name']+' · revision '+str(doc['revision']))
                st.json(s['assumptions'],expanded=True)
        with chart:
            draw_bars([(d['name']+' · '+d['budget_id'][:8],s['summary']['net']) for d,s in zip(docs,expected)],docs[0]['plan']['currency'],'Expected cumulative net by budget')
            st.dataframe([{'Budget':d['name'],'Revision':d['revision'],'Revenue':s['summary']['total_revenue'],
                'Cost':s['summary']['total_cost'],'Net':s['summary']['net']} for d,s in zip(docs,expected)],width='stretch')
    else: st.info('These plans have different currencies, start dates or horizons. Review each tab separately; combined totals would not be comparable.')
    for tab,doc,s in zip(st.tabs([d['name']+' · '+d['budget_id'][:8] for d in docs]),docs,expected):
        with tab:
            output,assumptions=st.columns([3,2])
            with assumptions:
                st.write('Full assumptions used · revision '+str(doc['revision']))
                st.json(s['assumptions'],expanded=True)
            with output:
                ccy=doc['plan']['currency']
                st.caption('Saved '+doc['updated_at']+' · '+str(doc['plan']['months'])+' months from '+doc['plan']['start_date'])
                draw_trend([dict(x,period_start=x['start']) for x in s['periods']],
                    [('revenue','Revenue'),('total_cost','Cost'),('net','Net')],ccy)
                st.dataframe([{k:v for k,v in x.items() if k not in ('staff','clinic_costs')} for x in s['periods']],width='stretch')
