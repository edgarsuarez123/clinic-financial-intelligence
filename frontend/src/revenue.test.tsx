import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Revenue from "./revenue";
const mocks=vi.hoisted(() => ({ api: vi.fn() }));
vi.mock("./api", async (original) => ({ ...await original<typeof import("./api")>(),
  api: (path:string) => path === "/analytics/metadata" ? Promise.resolve({clinic_locations:["North","South"]}) : mocks.api(path) }));
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

it("refetches revenue for an individual clinic and returns to the combined total",async()=>{
  mocks.api.mockResolvedValue(report);
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findByRole("option",{name:"North"});
  fireEvent.change(screen.getByLabelText("Clinic location"),{target:{value:"North"}});
  await waitFor(()=>expect(mocks.api).toHaveBeenLastCalledWith(expect.stringContaining("clinic_location=North")));
  fireEvent.change(screen.getByLabelText("Clinic location"),{target:{value:""}});
  await waitFor(()=>expect(mocks.api).toHaveBeenLastCalledWith("/analytics/revenue?start=2026-01-01&end=2026-03-31&frequency=month"));
});

it("hides the redundant category breakdown and filter for one available category", async () => {
  mocks.api.mockResolvedValue({
    ...report,
    options: { ...report.options, category: ["Collections"] },
  });
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findAllByText("$1,234.56");
  expect(screen.queryByLabelText("Revenue category")).toBeNull();
  expect(screen.queryByRole("heading", { name: "Revenue by revenue category" })).toBeNull();
  expect(screen.getByLabelText("Medical insurance")).toBeTruthy();
});

it("hides the category breakdown and filter when no categories are available", async () => {
  mocks.api.mockResolvedValue({
    ...report,
    options: { ...report.options, category: [] },
  });
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findAllByText("$1,234.56");
  expect(screen.queryByLabelText("Revenue category")).toBeNull();
  expect(screen.queryByRole("heading", { name: "Revenue by revenue category" })).toBeNull();
});

it("restores the category breakdown when multiple categories are available", async () => {
  mocks.api.mockResolvedValue({
    ...report,
    options: { ...report.options, category: ["Collections", "Procedures"] },
  });
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findAllByText("$1,234.56");
  expect(screen.getByLabelText("Revenue category")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Revenue by revenue category" })).toBeTruthy();
});

it("keeps an active category filter available to clear after the data narrows", async () => {
  const multiple = {
    ...report,
    options: { ...report.options, category: ["Collections", "Procedures"] },
  };
  const single = {
    ...report,
    total_revenue: "50.00",
    options: { ...report.options, category: ["Collections"] },
  };
  mocks.api.mockResolvedValueOnce(multiple).mockResolvedValue(single);
  render(<Revenue start="2026-01-01" end="2026-03-31" />);
  await screen.findAllByText("$1,234.56");
  fireEvent.change(screen.getByLabelText("Revenue category"), {
    target: { value: "v:Collections" },
  });
  await waitFor(() => expect(mocks.api).toHaveBeenLastCalledWith(
    "/analytics/revenue?start=2026-01-01&end=2026-03-31&frequency=month&category=Collections",
  ));
  await screen.findByText("$50.00");
  expect(screen.getByLabelText("Revenue category")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Revenue by revenue category" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  await waitFor(() => expect(screen.queryByLabelText("Revenue category")).toBeNull());
});

it("refetches the report when the completed-import data version changes", async () => {
  mocks.api.mockResolvedValue(report);
  const { rerender } = render(
    <Revenue start="2026-01-01" end="2026-03-31" dataVersion={0} />,
  );
  await screen.findAllByText("$1,234.56");
  const callsBeforeRefresh = mocks.api.mock.calls.length;
  rerender(<Revenue start="2026-01-01" end="2026-03-31" dataVersion={1} />);
  await waitFor(() => expect(mocks.api.mock.calls.length).toBeGreaterThan(callsBeforeRefresh));
});
