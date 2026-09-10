import {afterEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen} from "@testing-library/react";
import {Questions} from "./main";
const mocks=vi.hoisted(()=>({send:vi.fn()}));
vi.mock("./api",async(original)=>({...await original<typeof import("./api")>(),send:mocks.send}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const config={demo_questions:[],provider_access:true,disclosure:"Local processing",supported_questions:[],diagnostics_enabled:false};
it("shows readable results without production SQL, model costs or scope controls",async()=>{
  mocks.send.mockResolvedValue({status:"answered",answer:"Recorded monthly trends.",sql:"SELECT secret_sql",rows:[{margin_pct:"12.34567890123"}]});
  render(<Questions config={config} start="2026-01-01" end="2026-03-31"/>);
  fireEvent.change(screen.getByLabelText("Your financial question"),{target:{value:"Show monthly trends"}});
  fireEvent.click(screen.getByRole("button",{name:"Ask Clarity"}));
  expect(await screen.findByText("12.35%")).toBeTruthy();
  expect(screen.queryByText("Generated SQL")).toBeNull();
  expect(screen.queryByText("Grounded in your numbers")).toBeNull();
  expect(screen.queryByLabelText("Question scope")).toBeNull();
  expect(mocks.send.mock.calls[0][1].allow_provider_data).toBe(true);
});
it("keeps diagnostics in dev/test and does not show tables for refused requests",async()=>{
  mocks.send.mockResolvedValue({status:"refused",answer:"I cannot answer reliably.",rows:[{net:"123456"}]});
  render(<Questions config={{...config,diagnostics_enabled:true}} start="2026-01-01" end="2026-03-31"/>);
  fireEvent.change(screen.getByLabelText("Your financial question"),{target:{value:"Unsupported question"}});
  fireEvent.click(screen.getByRole("button",{name:"Ask Clarity"}));
  await screen.findByText("I cannot answer reliably.");
  expect(screen.getByText("Grounded in your numbers")).toBeTruthy();
  expect(screen.queryByText("123456")).toBeNull();
});

it("discards a pending answer after changing the reporting dates",async()=>{
  let resolve:(value:unknown)=>void=()=>{};
  mocks.send.mockImplementation(()=>new Promise(r=>{resolve=r;}));
  const view=render(<Questions config={config} start="2026-01-01" end="2026-03-31"/>);
  fireEvent.change(screen.getByLabelText("Your financial question"),{target:{value:"Show monthly trends"}});
  fireEvent.click(screen.getByRole("button",{name:"Ask Clarity"}));
  view.rerender(<Questions config={config} start="2026-04-01" end="2026-06-30"/>);
  await act(async()=>resolve({status:"answered",answer:"Old dates answer",rows:[]}));
  expect(screen.queryByText("Old dates answer")).toBeNull();
  expect((screen.getByRole("button",{name:"Ask Clarity"}) as HTMLButtonElement).disabled).toBe(false);
});
