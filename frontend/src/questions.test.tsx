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
  await screen.findByText('Connection lost');
  fireEvent.click(screen.getByRole('button',{name:'Retry send'}));
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
