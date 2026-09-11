import { useEffect,useRef,useState } from "react";
import { MessageSquare,Plus,Send,Trash2 } from "lucide-react";
import { api,send } from "./api";
import { Card,Chart,Evidence,Field,Notice,Table,Select } from "./components";
import ClinicSelect from "./clinic-select";
import type { Row } from "./types";

export default function Questions({config,start,end,onDraft}:{config:Row;start:string;end:string;onDraft?:(draft:Row)=>void}) {
  const [threads,setThreads]=useState<Row[]>([]),[thread,setThread]=useState<Row|null>(null);
  const [hasMore,setHasMore]=useState(false),[question,setQuestion]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [plans,setPlans]=useState<Row[]>([]),[budgetIds,setBudgetIds]=useState<string[]>([]),[clinic,setClinic]=useState('');
  const [title,setTitle]=useState(''),[costs,setCosts]=useState<Row|null>(null),[pending,setPending]=useState<Row|null>(null);
  const version=useRef(0),newId=useRef(crypto.randomUUID()),alive=useRef(true);
  useEffect(()=>{
    alive.current=true;
    const initialVersion=version.current,initialId=new URL(window.location.href).searchParams.get('chat');
    void list().then(async rows=>{
      if(!alive.current||version.current!==initialVersion)return;
      if(initialId||rows[0]) await open(initialId||rows[0].conversation_id);
    }).catch(e=>alive.current&&setError(e.message));
    if(config.simulation_access) api('/simulations/budgets').then(r=>alive.current&&setPlans(r.budgets)).catch(e=>alive.current&&setError(e.message));
    return ()=>{alive.current=false;version.current++;};
  },[]);
  async function list(offset=0) {
    const r=await api(`/questions/conversations?offset=${offset}`);
    if(alive.current){setThreads(t=>offset?[...t,...r.conversations]:r.conversations);setHasMore(r.has_more);}
    return r.conversations as Row[];
  }
  function location(id:string|null) {
    const url=new URL(window.location.href);if(id) url.searchParams.set('chat',id);else url.searchParams.delete('chat');
    window.history.replaceState(null,'',url);
  }
  async function open(id:string) {
    const v=++version.current;setError('');setBusy(true);setPending(null);
    try {
      const r=await api(`/questions/conversations/${id}`);
      if(alive.current&&v===version.current){setThread(r);setTitle(r.title);setBudgetIds(r.turns.at(-1)?.context.budget_ids||[]);setClinic(r.turns.at(-1)?.context.clinic_location||'');setQuestion('');location(id);}
    } catch(e){if(alive.current&&v===version.current)setError((e as Error).message);}
    finally {if(alive.current&&v===version.current)setBusy(false);}
  }
  function fresh() {version.current++;newId.current=crypto.randomUUID();setThread(null);setTitle('');setQuestion('');setError('');setPending(null);setBusy(false);setBudgetIds([]);location(null);}
  async function ask(retry?:Row) {
    if(busy)return;
    const v=++version.current;setBusy(true);setError('');
    const captured=retry||pending||{turn_id:crypto.randomUUID(),question:question.trim(),context:{start,end,clinic_location:clinic||null,budget_ids:budgetIds}};
    setPending(captured);
    try {
      let current=thread;
      if(!current){current=await send('/questions/conversations',{conversation_id:newId.current,title:captured.question.slice(0,100)});if(alive.current&&v===version.current){setThread(current);setTitle(current!.title);location(current!.conversation_id);}}
      const r=await send(`/questions/conversations/${current!.conversation_id}/turns`,{...captured,expected_revision:current!.revision});
      if(alive.current&&v===version.current){setThread(r);setQuestion('');setPending(null);await list();}
    }catch(e){if(alive.current&&v===version.current)setError((e as Error).message);}
    finally{if(alive.current&&v===version.current)setBusy(false);}
  }
  async function rename() {
    if(!thread||!title.trim())return;setError('');
    try{await send(`/questions/conversations/${thread.conversation_id}`,{title,expected_revision:thread.revision},'PATCH');await open(thread.conversation_id);await list();}catch(e){setError((e as Error).message);}
  }
  async function remove() {
    if(!thread||!window.confirm('Delete this conversation from your history?'))return;
    try{await send(`/questions/conversations/${thread.conversation_id}`,{expected_revision:thread.revision},'DELETE');fresh();await list();}catch(e){setError((e as Error).message);}
  }
  return <div className="chat-workspace">
    <aside className="chat-sidebar"><button className="primary" onClick={fresh} disabled={busy}><Plus size={16}/>New conversation</button>
      <h2>Conversations</h2><div className="thread-list">{threads.map(t=><button className="chat-thread" key={t.conversation_id} disabled={busy} aria-current={thread?.conversation_id===t.conversation_id?'page':undefined} onClick={()=>void open(t.conversation_id)}>{t.title}</button>)}</div>
      {!threads.length&&<p className="fine">Your conversations will appear here.</p>}
      {hasMore&&<button onClick={()=>void list(threads.length).catch(e=>setError(e.message))}>More conversations</button>}
    </aside>
    <div className="chat-main">
      {thread&&<details><summary>Conversation settings</summary><Field label="Conversation name" value={title} onChange={setTitle}/><button disabled={busy} onClick={()=>void rename()}>Rename</button><button disabled={busy} onClick={()=>void remove()}><Trash2 size={15}/>Delete conversation</button></details>}
      <div className="chat-context"><span>{start||'Choose dates'} → {end}</span><span>{clinic||'All clinics'}</span>{budgetIds.map(id=><span key={id}>{plans.find(p=>p.budget_id===id)?.name||'Attached saved plan'}</span>)}</div>
      <details className="chat-attachments"><summary>Attach saved plans or select clinic</summary><ClinicSelect value={clinic} onChange={setClinic}/>
        {config.simulation_access&&<><Select label="Attach saved plan" value="" onChange={id=>id&&setBudgetIds(ids=>ids.includes(id)?ids:[...ids,id].slice(0,3))} options={[["","Choose a plan"],...plans.map(p=>[p.budget_id,p.name] as [string,string])]}/>
        {budgetIds.map(id=><button key={id} type="button" onClick={()=>setBudgetIds(ids=>ids.filter(x=>x!==id))}>Detach {plans.find(p=>p.budget_id===id)?.name||'plan'}</button>)}</>}
      </details>
      {error&&<Notice error>{error}{thread&&<button disabled={busy} onClick={()=>void open(thread.conversation_id)}>Reopen conversation</button>}</Notice>}
      <div className="chat-messages" aria-label="Conversation messages">
        {!thread?.turns?.length&&<Card><MessageSquare size={28}/><h2>What would you like to understand?</h2><p>Explore your revenue, compare saved plans, or test a financial change.</p><div className="chat-suggestions">{['Show monthly revenue and expenses','Compare my attached scenarios','What should I review in these financial results?'].map(q=><button key={q} onClick={()=>setQuestion(q)}>{q}</button>)}</div></Card>}
        {thread?.turns?.map((turn:Row)=><div key={turn.turn_id}><article className="chat-message user">{turn.question}</article>
          <div className="chat-context"><small>{turn.context.start} – {turn.context.end} · {turn.context.clinic_location||'All clinics'}</small></div>
          {turn.status==='running'?<Notice>Reply is processing. <button disabled={busy} onClick={()=>void open(thread.conversation_id)}>Check reply</button><button disabled={busy} onClick={()=>void ask({turn_id:turn.turn_id,question:turn.question,context:turn.context})}>Retry interrupted reply</button></Notice>:<Reply value={turn.response} diagnostics={!!config.diagnostics_enabled} onDraft={onDraft}/>}</div>)}
        {busy&&<p role="status">Clarity is checking your data. Local models can take up to five minutes.</p>}
      </div>
      <div className="chat-composer"><form onSubmit={e=>{e.preventDefault();void ask();}}><label><span className="sr-only">Your financial question</span><textarea required maxLength={2000} value={question} onChange={e=>{setQuestion(e.target.value);setPending(null);}} placeholder="Ask a question or follow up…" disabled={busy}/></label><button className="primary" disabled={busy||!start||!end||(!question.trim()&&!pending)}><Send size={17}/>{pending&&!busy?'Retry send':'Ask Clarity'}</button></form>
        <details className="fine"><summary>Data processing</summary>{config.disclosure} Saved conversations and attached scenario context are included. Do not enter patient identifiers.</details>
      </div>
      {config.diagnostics_enabled&&<Card title="Development diagnostics"><p>{config.provider_name} · {config.model}</p>{config.cost_report_access&&<button onClick={()=>void api(`/questions/costs?start=${start}&end=${end}`).then(setCosts).catch(e=>setError(e.message))}>View model usage & costs</button>}{costs&&<Table rows={costs.rows}/>}</Card>}
    </div>
  </div>;
}
function Reply({value,diagnostics,onDraft}:{value:Row;diagnostics:boolean;onDraft?: (draft:Row)=>void}) {
  if(!value)return null;
  return <article className="chat-message assistant"><h3>Clarity</h3><p className="answer-text">{value.answer}</p>
    {value.status==='answered'&&<>
      {value.tables?.map((t:Row,i:number)=><section key={i}><h3>{t.title}</h3>{t.chart!=='table'&&t.rows.length>0&&t.keys?.length>0&&<Chart rows={t.rows} keys={t.keys} x={t.x} bar={t.chart==='bar'} currency={t.rows[0]?.currency}/> }<Table rows={t.rows} columns={t.columns}/></section>)}
      {!!value.interpretation?.length&&<section className="inference"><h3>AI interpretation</h3>{value.interpretation.map((r:Row,i:number)=><div key={i}><p>{r.text}</p><Evidence value={value.facts.filter((f:Row)=>r.evidence.includes(f.id))} label="Supporting values"/></div>)}</section>}
      {!!value.recommendations?.length&&<section className="inference"><h3>Considerations, based on these results</h3>{value.recommendations.map((r:Row,i:number)=><div key={i}><p>{r.text}</p><Evidence value={value.facts.filter((f:Row)=>r.evidence.includes(f.id))} label="Supporting values"/></div>)}</section>}
      {value.narration_unavailable&&<p className="fine">The calculations are available; AI interpretation was unavailable or could not be verified.</p>}
      {value.forecast&&<details><summary>Forecast basis and validation</summary><p>{value.forecast.basis}</p><Table rows={[{method:value.forecast.method,history_months:value.forecast.history_months,validation_mae:value.forecast.validation_mae,benchmark_mae:value.forecast.benchmark_mae}]}/></details>}
      {value.draft&&<div className="baseline-review"><h3>Proposed plan · not applied</h3><Evidence value={value.draft.changes} label="Review proposed changes"/><button className="primary" disabled={!onDraft} onClick={()=>onDraft?.(value.draft)}>Open as a new plan</button></div>}
      <div className="chat-evidence">{value.sources?.map((s:Row,i:number)=><p key={i}>{s.kind==='saved_plan'?`${s.name} · saved revision ${s.revision}`:`Recorded data · ${s.start} – ${s.end} · ${s.clinic_location||'All clinics'}`}</p>)}<small>Answered {value.as_of?.slice(0,16).replace('T',' ')} UTC. Saved answers retain the values used at the time.</small></div>
    </>}
    {diagnostics&&<Evidence value={{sql:value.sql,parameters:value.parameters,data_revision:value.data_revision}} label="Query diagnostics"/>}
  </article>;
}
