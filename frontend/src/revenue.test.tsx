import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Revenue from "./revenue";
const mocks=vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("./api", async (original) => ({ ...await original<typeof import("./api")>(), api: mocks.api }));
vi.mock("./plots", () => ({ default: () => <div>Chart</div> }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const report = {
  currency: "USD", total_revenue: "1234.56", row_count: 2,
  periods: [{ period_start: "2026-01-01", coverage_start: "2026-01-01", coverage_end: "2026-03-31", partial: false, revenue: "1234.56" }],
  options: { medical_insurance: ["Demo A", ""], billing_code: ["C1"], category: ["Collections"] },
  breakdowns: { medical_insurance: [{ label: "Demo A", revenue: "1234.56" }], billing_code: [{ label: "C1", revenue: "1234.56" }], category: [{ label: "Collections", revenue: "1234.56" }] },
};
it("requests combined quarter and insurer filters and renders readable exact amounts", async () => {
  mocks.api.mockResolvedValue(report);
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  expect((await screen.findAllByText("$1,234.56")).length).toBeGreaterThan(1);
  fireEvent.change(screen.getByLabelText("Group dates by"), { target: { value: "quarter" } });
  await waitFor(() => expect(mocks.api).toHaveBeenLastCalledWith(expect.stringContaining("frequency=quarter")));
  await screen.findAllByText("$1,234.56");
  fireEvent.change(screen.getByLabelText("Medical insurance"), { target: { value: "v:Demo A" } });
  await waitFor(() => expect(mocks.api).toHaveBeenLastCalledWith(expect.stringContaining("medical_insurance=Demo+A")));
  await screen.findAllByText("$1,234.56");
  fireEvent.change(screen.getByLabelText("Billing code"), { target: { value: "v:C1" } });
  await waitFor(() => expect(mocks.api).toHaveBeenLastCalledWith(expect.stringContaining("medical_insurance=Demo+A&billing_code=C1")));
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  await waitFor(() => expect(mocks.api).toHaveBeenLastCalledWith("/analytics/revenue?start=2026-01-01&end=2026-03-31&frequency=quarter"));
});
it("shows errors without retaining stale financial totals", async () => {
  mocks.api.mockRejectedValue(new Error("Select a smaller date range."));
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  expect((await screen.findByRole("alert")).textContent).toContain("Select a smaller date range");
  expect(screen.queryByText("$1,234.56")).toBeNull();
});
it("updates displayed totals and retains filter choices while requests are pending", async () => {
  let resolve: (value: typeof report) => void = () => {};
  mocks.api.mockResolvedValueOnce(report).mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findAllByText('$1,234.56');
  fireEvent.change(screen.getByLabelText('Medical insurance'),{target:{value:'v:Demo A'}});
  expect(screen.queryByText('$1,234.56')).toBeNull();
  expect(screen.getByRole('option',{name:'C1'})).toBeTruthy();
  resolve({...report,total_revenue:'50.00'});
  expect(await screen.findByText('$50.00')).toBeTruthy();
});
it("ignores an older response arriving after the newest filter result",async()=>{
  let old: (value: typeof report)=>void=()=>{};
  mocks.api.mockImplementationOnce(()=>new Promise(r=>{old=r;})).mockResolvedValueOnce({...report,total_revenue:'25.00'});
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  fireEvent.change(screen.getByLabelText('Group dates by'),{target:{value:'week'}});
  await screen.findByText('$25.00');
  old({...report,total_revenue:'999.00'});
  await waitFor(()=>expect(screen.queryByText('$999.00')).toBeNull());
});
