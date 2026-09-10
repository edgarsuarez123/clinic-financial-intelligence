import {afterEach,expect,it,vi} from "vitest";
import {cleanup,render,screen} from "@testing-library/react";
import {Overview} from "./main";
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock("./api",async(original)=>({...await original<typeof import("./api")>(),api:mocks.api}));
vi.mock("./plots",()=>({default:()=> <div>Chart</div>}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
it("shows rounded margins and clinic totals without coverage clutter",async()=>{
  const summary={revenue:"100",expense:"30",net:"70",margin_pct:"70.123456789",categories:[]};
  mocks.api.mockImplementation(async(path:string)=>path.includes("metadata")?{clinic_locations:["North"]}:
    path.includes("locations?")?{rows:[{clinic_location:"North",revenue:"100",expense:"30",net:"70",currency:"USD"}]}:
    {summary,currency:"USD",monthly:[{...summary,period_start:"2026-01-01"}],weekly:[],category_labels:{},
      data_notes:["Totals describe imported records, not a certification of complete books."],volatility:{revenue:{value:".1"},expense:{value:".2"}}});
  render(<Overview start="2026-01-01" end="2026-01-31"/>);
  expect((await screen.findAllByText("70.12%")).length).toBe(2);
  expect(screen.queryByText("Exact averages and window coverage")).toBeNull();
  expect(screen.queryByText(/Totals describe imported records/)).toBeNull();
  expect(screen.queryByRole("columnheader",{name:"activity"})).toBeNull();
  expect(screen.queryByRole("columnheader",{name:"date coverage"})).toBeNull();
  expect(screen.getByRole("heading",{name:"Revenue & expenses by clinic"})).toBeTruthy();
});
