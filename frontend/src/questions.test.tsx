import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import Questions from "./clarity";
const mocks=vi.hoisted(()=>({api:vi.fn(),send:vi.fn()}));
vi.mock("./api",async(original)=>({...await original<typeof import("./api")>(),api:mocks.api,send:mocks.send}));
const config={simulation_access:false,disclosure:"Local processing",diagnostics_enabled:false};
const context={start:"2026-01-01",end:"2026-03-31",clinic_location:null,budget_ids:[]};
let stored:any;
beforeEach(()=>{
  stored=null;window.history.replaceState(null,'','/');
  mocks.api.mockImplementation(async(path:string)=>path.includes('offset=')?{conversations:stored?[stored]:[],has_more:false}:path.includes('/questions/conversations/')?structuredClone(stored):{clinic_locations:[]});
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    if(path==='/questions/conversations'){stored={conversation_id:body.conversation_id,title:body.title,revision:1,turns:[]};return structuredClone(stored);}
    stored={...stored,revision:stored.revision+1,turns:[...stored.turns,{...body,status:'answered',response:{status:'answered',answer:'Recorded monthly trends.',sql:'SELECT secret_sql',tables:[{title:'Results',chart:'table',rows:[{margin_pct:'12.34567890123'}],columns:['margin_pct']}],sources:[],as_of:'2026-09-10T12:00:00Z'}}]};
    return structuredClone(stored);
  });
});
afterEach(()=>{cleanup();vi.resetAllMocks();window.history.replaceState(null,'','/');});
async function submit(text='Show monthly trends'){
  fireEvent.change(screen.getByLabelText("Your financial question"),{target:{value:text}});
  fireEvent.click(screen.getByRole("button",{name:"Ask Clarity"}));
  await screen.findByText("Recorded monthly trends.");
}
it("persists a conversation, reopens it after remount and hides production diagnostics",async()=>{
  const view=render(<Questions config={config} start={context.start} end={context.end}/>);
  await submit();
  expect(screen.getByText("12.35%")).toBeTruthy();
  expect(screen.queryByText("Query diagnostics")).toBeNull();
  expect(screen.queryByText("Development diagnostics")).toBeNull();
  expect(screen.queryByLabelText("Question scope")).toBeNull();
  const posted=mocks.send.mock.calls.find(c=>c[0].endsWith('/turns'))![1];
  expect(posted.context.start).toBe(context.start);expect(posted.turn_id).toBeTruthy();
  view.unmount();
  render(<Questions config={config} start={context.start} end={context.end}/>);
  expect(await screen.findByText("Recorded monthly trends.")).toBeTruthy();
  expect(stored.turns).toHaveLength(1);
});
it("sends follow-ups with the current conversation revision and retains earlier scope",async()=>{
  const view=render(<Questions config={config} start={context.start} end={context.end}/>);
  await submit();
  view.rerender(<Questions config={config} start="2026-04-01" end="2026-06-30"/>);
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Now compare this quarter'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  await waitFor(()=>expect(stored.turns).toHaveLength(2));
  expect(stored.turns[0].context.start).toBe('2026-01-01');
  expect(stored.turns[1].context.start).toBe('2026-04-01');
  expect(stored.turns[1].expected_revision).toBe(2);
});
it("keeps dev diagnostics and hides result tables when a request was refused",async()=>{
  stored={conversation_id:'chat1',revision:2,title:'Review',turns:[{turn_id:'t',question:'Unsupported',context,status:'refused',response:{status:'refused',answer:'I cannot answer reliably.',tables:[{rows:[{net:'123456'}]}]}}]};
  render(<Questions config={{...config,diagnostics_enabled:true}} start={context.start} end={context.end}/>);
  expect(await screen.findByText('I cannot answer reliably.')).toBeTruthy();
  expect(screen.getByText('Development diagnostics')).toBeTruthy();
  expect(screen.queryByText('123456')).toBeNull();
});
it("reuses the same message ID after a lost response instead of duplicating the turn",async()=>{
  let first=true;let attempted:any;
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    if(path==='/questions/conversations'){stored={conversation_id:'chat1',title:'Review',revision:1,turns:[]};return stored;}
    if(first){first=false;attempted=structuredClone(body);throw new Error('Connection lost');}
    expect(body.turn_id).toBe(attempted.turn_id);expect(body.context).toEqual(attempted.context);
    return {...stored,revision:2,turns:[{...body,status:'answered',response:{status:'answered',answer:'Recovered',tables:[],sources:[]}}]};
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Show monthly trends'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  await waitFor(()=>expect(screen.getAllByRole('button',{name:'Retry send'}).length).toBeGreaterThan(0));
  fireEvent.click(screen.getAllByRole('button',{name:'Retry send'})[0]);
  expect(await screen.findByText('Recovered')).toBeTruthy();
});
it("offers a proposed plan for explicit opening without saving it through chat",async()=>{
  const draft={name:'Higher rent',plan:{},changes:[]};const open=vi.fn();
  stored={conversation_id:'chat1',revision:2,title:'Plan',turns:[{turn_id:'t',question:'What if rent rises?',context,status:'answered',response:{status:'answered',answer:'Proposed',tables:[],sources:[],draft}}]};
  render(<Questions config={config} start={context.start} end={context.end} onDraft={open}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Open as a new plan'}));
  expect(open).toHaveBeenCalledWith(draft);
  expect(mocks.send).not.toHaveBeenCalled();
});

it("shows the submitted question and pending assistant bubble before a reply arrives",async()=>{
  let resolveTurn!: (value:any)=>void;
  const turnResult=new Promise((resolve)=>{resolveTurn=resolve;});
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    if(path==='/questions/conversations'){
      stored={conversation_id:body.conversation_id,title:body.title,revision:1,turns:[]};
      return structuredClone(stored);
    }
    const result=await turnResult;
    stored=result;
    return structuredClone(result);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  const text='Show the answer while the model works';
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:text}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  expect((await screen.findByRole('article',{name:'Your question'})).textContent).toContain(text);
  expect(screen.getByRole('article',{name:'Clarity reply pending'})).toBeTruthy();
  expect(screen.queryByText('Recorded monthly trends.')).toBeNull();
  resolveTurn({conversation_id:stored.conversation_id,title:stored.title,revision:2,turns:[{turn_id:'sent',position:1,question:text,context,status:'answered',response:{status:'answered',answer:'Arrived after pending.',tables:[],sources:[]}}]});
  expect(await screen.findByText('Arrived after pending.')).toBeTruthy();
});

it("restores a running turn and retries that exact ID when reopened",async()=>{
  const running={turn_id:'running-turn',position:1,question:'Still processing?',context,status:'running',response:null};
  stored={conversation_id:'chat1',revision:2,title:'Review',turns:[running]};
  let retried:any;
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    retried=structuredClone(body);
    stored={...stored,revision:2,turns:[{...running,status:'answered',response:{status:'answered',answer:'Recovered after reopen.',tables:[],sources:[]}}]};
    return structuredClone(stored);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  expect(await screen.findByRole('article',{name:'Clarity reply pending'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Check reply'}));
  expect(await screen.findByText('Recovered after reopen.')).toBeTruthy();
  expect(retried.turn_id).toBe('running-turn');
});

it("keeps a failed question in order while a later question succeeds",async()=>{
  stored={conversation_id:'chat1',revision:2,title:'Review',turns:[{turn_id:'old',position:1,question:'Earlier',context,status:'answered',response:{status:'answered',answer:'Earlier answer',tables:[],sources:[]}}]};
  let first=true;
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    if(first){
      first=false;
      throw new Error('Connection lost');
    }
    stored={...stored,revision:3,turns:[...stored.turns,{turn_id:'later',position:2,question:body.question,context:body.context,status:'answered',response:{status:'answered',answer:'Later answer',tables:[],sources:[]}}]};
    return structuredClone(stored);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  await screen.findByText('Earlier answer');
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Failed first question'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  await waitFor(()=>expect(screen.getAllByRole('button',{name:'Retry send'}).length).toBeGreaterThan(0));
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Later question'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  expect(await screen.findByText('Later answer')).toBeTruthy();
  const turns=screen.getAllByRole('article');
  expect(turns.findIndex((item)=>item.textContent?.includes('Failed first question'))).toBeLessThan(turns.findIndex((item)=>item.textContent?.includes('Later answer')));
  expect(screen.getAllByText('Connection lost').length).toBeGreaterThan(0);
});

it("starts a fresh turn for a saved unavailable response",async()=>{
  const unavailable={turn_id:'unavailable-turn',position:1,question:'Try the model',context,status:'unavailable',response:{status:'unavailable',answer:'Model unavailable.',tables:[],sources:[]}};
  stored={conversation_id:'chat1',revision:2,title:'Review',turns:[unavailable]};
  let retried:any;
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    retried=structuredClone(body);
    stored={...stored,revision:3,turns:[...stored.turns,{turn_id:'fresh-turn',position:2,question:body.question,context:body.context,status:'answered',response:{status:'answered',answer:'Fresh model reply.',tables:[],sources:[]}}]};
    return structuredClone(stored);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Start a fresh attempt'}));
  expect(await screen.findByText('Fresh model reply.')).toBeTruthy();
  expect(retried.turn_id).not.toBe('unavailable-turn');
  expect(screen.getByText('Model unavailable.')).toBeTruthy();
});

it("keeps a successful answer when the post-send history refresh fails",async()=>{
  stored={conversation_id:'chat1',revision:1,title:'Review',turns:[]};
  let listCalls=0;
  mocks.api.mockImplementation(async(path:string)=>{
    if(path.includes('offset=')){
      listCalls++;
      if(listCalls===2) throw new Error('History refresh lost');
      return {conversations:[{conversation_id:'chat1',title:'Review',revision:1}],has_more:false};
    }
    if(path.includes('/questions/conversations/')) return structuredClone(stored);
    return {clinic_locations:[]};
  });
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    stored={...stored,revision:2,turns:[{turn_id:body.turn_id,position:1,question:body.question,context:body.context,status:'answered',response:{status:'answered',answer:'Saved despite refresh failure.',tables:[],sources:[]}}]};
    return structuredClone(stored);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  await screen.findByText('Review');
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Show monthly trends'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  expect(await screen.findByText('Saved despite refresh failure.')).toBeTruthy();
  expect(screen.queryByRole('article',{name:'Clarity reply failed'})).toBeNull();
  expect(screen.getAllByText('History refresh lost').length).toBeGreaterThan(0);
});

it("ignores a stale history reply after starting a new conversation",async()=>{
  let resolveList!: (value:any)=>void;
  const listResult=new Promise((resolve)=>{resolveList=resolve;});
  mocks.api.mockImplementation(async(path:string)=>{
    if(path.includes('offset=')) return listResult;
    return {clinic_locations:[]};
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  fireEvent.click(screen.getByRole('button',{name:'New conversation'}));
  resolveList({conversations:[{conversation_id:'stale',title:'Stale conversation',revision:1}],has_more:false});
  await waitFor(()=>expect(screen.queryByRole('button',{name:'Stale conversation'})).toBeNull());
  expect(screen.queryByText('Stale conversation')).toBeNull();
});

it("does not replace an unsent draft when retrying an older failed turn",async()=>{
  stored={conversation_id:'chat1',revision:1,title:'Review',turns:[]};
  let first=true;
  mocks.send.mockImplementation(async(path:string,body:any)=>{
    if(first){ first=false; throw new Error('Connection lost'); }
    stored={...stored,revision:2,turns:[{turn_id:body.turn_id,position:1,question:body.question,context:body.context,status:'answered',response:{status:'answered',answer:'Retried answer.',tables:[],sources:[]}}]};
    return structuredClone(stored);
  });
  render(<Questions config={config} start={context.start} end={context.end}/>);
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Original failed question'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask Clarity'}));
  await waitFor(()=>expect(screen.getAllByRole('button',{name:'Retry send'}).length).toBeGreaterThan(0));
  fireEvent.change(screen.getByLabelText('Your financial question'),{target:{value:'Unsent draft'}});
  fireEvent.click(screen.getAllByRole('button',{name:'Retry send'})[0]);
  expect(await screen.findByText('Retried answer.')).toBeTruthy();
  expect((screen.getByLabelText('Your financial question') as HTMLTextAreaElement).value).toBe('Unsent draft');
});
