"""Explicit external-processing disclosure and inspectable quantitative answers."""
import streamlit as st

def render_questions(call,message,token):
    st.header('Ask about clinic finances')
    st.caption('This assistant analyzes recorded transactions. It cannot create, edit, or compare saved budgets through chat yet. Use Staffing & clinic budget for editable inputs, scenario charts, and budget tables.')
    status,options=call('GET','/api/v1/questions/config',token)
    if status!=200: message(options); return
    st.info(options['disclosure'])
    if not options['enabled']:
        st.info('Financial questions are disabled until the provider, written disclosure, DPA, pricing and account access are configured.'); return
    if options.get('demo_questions'):
        st.write('Fixed demo questions:')
        for question in options['demo_questions']: st.code(question,language=None)
    st.caption('Provider: '+str(options['provider_name'])+' · Model: '+str(options['model']))
    if options['synthetic_data']: st.warning('Synthetic demonstration only. Do not enter real clinic or patient data.')
    with st.expander('Supported questions and limitations',expanded=True):
        for description in options['supported_questions']: st.write('• '+description)
        st.write('Other questions are refused. Select the exact period below; ambiguous or conflicting dates are not inferred.')
    st.caption('Allow roughly 10–60 seconds for a new answer. Repeated identical questions may use a cached snapshot for '+str(options['cache_seconds'])+' seconds. Clinic-wide limit: '+str(options['requests_per_window'])+' questions per '+str(options['window_seconds'])+' seconds.')
    with st.form('financial_question'):
        question=st.text_area('Your question',max_chars=1000,placeholder='What were revenue, expenses and net margin for the selected period?')
        left,right=st.columns(2)
        start=left.date_input('Period start',value=None)
        end=right.date_input('Period end',value=None)
        providers=st.checkbox('Include provider identifiers and recorded attributed costs',disabled=not options['provider_access'])
        consent=st.checkbox('This question contains no patient identifiers. I acknowledge the external financial-data processing described above.')
        submit=st.form_submit_button('Ask financial question')
    if submit:
        st.session_state.pop('financial_answer',None)
        if not consent or not start or not end or not question.strip():
            st.error('Enter a question, select both dates and acknowledge external processing.')
        else:
            with st.spinner('Translating the question, querying the database and preparing a grounded answer…'):
                status,result=call('POST','/api/v1/questions',token,json={'question':question,'start':start.isoformat(),'end':end.isoformat(),
                    'allow_provider_data':providers,'acknowledge_external_processing':True})
            if 'answer' in result:
                st.session_state.financial_answer={'result':result,'provider_data':providers}
            else: message(result)
    saved=st.session_state.get('financial_answer')
    if saved and (not saved['provider_data'] or options['provider_access']):
        result=saved['result']
        if result['status']=='answered':
            st.write(result['answer'])
            st.caption('Interpretation: '+result['interpretation'])
            st.caption('Snapshot: '+result['as_of']+' · data revision '+str(result['data_revision'])+(' · cached' if result['cached'] else ''))
            st.caption(result['limitations'])
        else: st.warning(result['answer'])
        if result.get('sql'):
            st.write('Generated SQL (unexecuted if translation was refused)')
            st.code(result['sql'],language='sql')
            st.write('Bound parameters'); st.json(result.get('parameters'))
        if result.get('rows') is not None:
            st.write('Raw database results — monetary values retain decimal precision')
            st.dataframe(result['rows'],width='stretch')
    if options['cost_report_access']:
        with st.expander('Clinic LLM usage and estimated cost'):
            left,right=st.columns(2)
            first=left.date_input('Usage start',value=None)
            last=right.date_input('Usage end',value=None)
            if st.button('Load usage report'):
                if not first or not last: st.error('Select the usage date range.')
                else:
                    status,result=call('GET','/api/v1/questions/costs',token,params={'start':first.isoformat(),'end':last.isoformat()})
                    if status==200: st.dataframe(result['rows'],width='stretch'); st.caption(result['note'])
                    else: message(result)
