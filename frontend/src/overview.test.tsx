import {afterEach,expect,it,vi} from "vitest";
import {cleanup,render,screen,waitFor} from "@testing-library/react";
import {Overview} from "./main";
import OverviewView from "./overview";
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

it("uses readable average headings and optional cost-variation help", async () => {
  const summary = {
    revenue: "100",
    expense: "30",
    net: "70",
    margin_pct: "70.123456789",
    fixed_cost: "10",
    variable_cost: "20",
    categories: [],
  };
  mocks.api.mockImplementation(async (path: string) =>
    path.includes("metadata")
      ? { clinic_locations: [] }
      : path.includes("locations?")
        ? { rows: [] }
        : {
            summary,
            currency: "USD",
            monthly: [],
            weekly: [
              {
                period_start: "2026-01-05",
                revenue_ma_4: { value: "25.125" },
                revenue_ma_12: { value: "20.00" },
              },
            ],
            category_labels: {},
            volatility: {
              basis: "Observed calendar weeks",
              missing_weeks: 0,
              partial_weeks: 0,
              revenue: { value: "0.1", samples: 1 },
              expense: { value: "0.2", samples: 1 },
            },
          },
  );
  render(<OverviewView start="2026-01-01" end="2026-01-31" />);
  expect(await screen.findByRole("columnheader", { name: "4-week average" })).toBeTruthy();
  expect(screen.getByRole("columnheader", { name: "12-week average" })).toBeTruthy();
  expect(screen.queryByText("average_4")).toBeNull();
  expect(screen.queryByText("average_12")).toBeNull();
  expect(screen.getByRole("heading", { name: "Costs and week-to-week variation" })).toBeTruthy();
});

it("refetches overview reports when the completed-import data version changes", async () => {
  const summary = { revenue: "100", expense: "30", net: "70", margin_pct: "70" };
  mocks.api.mockImplementation(async (path: string) =>
    path.includes("metadata")
      ? { clinic_locations: [] }
      : path.includes("locations?")
        ? { rows: [] }
        : {
            summary,
            currency: "USD",
            monthly: [],
            weekly: [],
            category_labels: {},
            volatility: { revenue: {}, expense: {} },
          },
  );
  const { rerender } = render(
    <OverviewView start="2026-01-01" end="2026-01-31" dataVersion={0} />,
  );
  await screen.findByRole("heading", { name: "Costs and week-to-week variation" });
  const dashboardCallsBeforeRefresh = mocks.api.mock.calls.filter(([path]) =>
    String(path).startsWith("/analytics/dashboard"),
  ).length;
  rerender(<OverviewView start="2026-01-01" end="2026-01-31" dataVersion={1} />);
  await waitFor(() => expect(mocks.api.mock.calls.filter(([path]) =>
    String(path).startsWith("/analytics/dashboard"),
  ).length).toBeGreaterThan(dashboardCallsBeforeRefresh));
});
