import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import Budgets from "./budgets";
import { newPlan } from "./types";
const mocks = vi.hoisted(() => ({ api: vi.fn(), send: vi.fn() }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  api: mocks.api,
  send: mocks.send,
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("loads current revenue and expenses without adding existing staff twice", async () => {
  mocks.api.mockImplementation(async (path: string) => path.includes("baseline?") ? {
    currency: "USD", existing_monthly_revenue: "50000", basis: "Recorded average",
    costs: [{ label: "Payroll", monthly_amount: "20000" }],
  } : path.includes("metadata") ? { first_date: "2026-01-01", last_date: "2026-03-31" }
    : { budgets: [], has_more: false });
  mocks.send.mockResolvedValue({ scenarios: [] });
  render(<Budgets historicalAccess={false} analyticsAccess />);
  await waitFor(() => expect((screen.getByLabelText("Baseline through") as HTMLInputElement).value).toBe("2026-03-31"));
  fireEvent.click(screen.getByRole("button", { name: "Use current financials" }));
  await screen.findByText(/Current revenue and costs loaded/);
  fireEvent.click(screen.getByRole("button", { name: "Run projection" }));
  await waitFor(() => expect(mocks.send).toHaveBeenCalled());
  const plan = mocks.send.mock.calls[0][1];
  expect(plan.existing_monthly_revenue).toBe("50000");
  expect(plan.staff).toEqual([]);
  expect(plan.clinic_costs[0].monthly_amount).toBe("20000");
  expect(plan.start_date).toBe("2026-04-01");
});
it("sends month-specific revenue and expense overrides and resets them",async()=>{
  mocks.api.mockResolvedValue({budgets:[],has_more:false});
  mocks.send.mockResolvedValue({scenarios:[]});
  render(<Budgets historicalAccess={false}/>);
  fireEvent.click(screen.getByRole("button",{name:"Add cost"}));
  fireEvent.change(screen.getByLabelText("Month 2 revenue"),{target:{value:"15000.25"}});
  fireEvent.change(screen.getByLabelText("Month 2 New cost"),{target:{value:"3000.50"}});
  fireEvent.click(screen.getByRole("button",{name:"Run projection"}));
  await waitFor(()=>expect(mocks.send).toHaveBeenCalled());
  expect(mocks.send.mock.calls[0][1].existing_revenue_by_month).toEqual({2:"15000.25"});
  expect(mocks.send.mock.calls[0][1].clinic_costs[0].monthly_amounts).toEqual({2:"3000.50"});
  fireEvent.click(screen.getByRole("button",{name:"Reset monthly overrides"}));
  expect((screen.getByLabelText("Month 2 revenue") as HTMLInputElement).value).toBe("0");
  expect(screen.queryByText("Projection formulas")).toBeNull();
});
it("saves editable decimal inputs and uses revisions when reopening", async () => {
  const plan = newPlan();
  plan.existing_revenue_basis = "Synthetic revenue";
  const saved = {
    budget_id: "abc",
    revision: 3,
    name: "Saved clinic",
    plan,
    result: { scenarios: [] },
    updated_at: "2026-09-08",
  };
  mocks.api.mockImplementation(async (path: string) =>
    path === "/simulations/budgets/abc"
      ? saved
      : { budgets: [saved], has_more: false },
  );
  mocks.send.mockResolvedValue({ ...saved, revision: 4 });
  render(<Budgets historicalAccess={false} />);
  fireEvent.click(
    await screen.findByRole("button", { name: /Saved clinic Revision/ }),
  );
  await waitFor(() =>
    expect((screen.getByLabelText("Plan name") as HTMLInputElement).value).toBe(
      "Saved clinic",
    ),
  );
  fireEvent.change(screen.getByLabelText("Existing monthly clinic revenue"), {
    target: { value: "1234.56" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
  await waitFor(() => expect(mocks.send).toHaveBeenCalled());
  const [path, body, method] = mocks.send.mock.calls[0];
  expect(path).toBe("/simulations/budgets/abc");
  expect(method).toBe("PUT");
  expect(body.expected_revision).toBe(3);
  expect(body.plan.existing_monthly_revenue).toBe("1234.56");
});
it("shows conflicts without discarding edited inputs", async () => {
  mocks.api.mockResolvedValue({ budgets: [], has_more: false });
  mocks.send.mockRejectedValue(
    new Error("This budget changed since you opened it."),
  );
  render(<Budgets historicalAccess={false} />);
  fireEvent.change(screen.getByLabelText("Revenue source / assumption"), {
    target: { value: "Explicit synthetic assumption" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save plan" }));
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "This budget changed since you opened it.",
  );
  expect(
    (screen.getByLabelText("Revenue source / assumption") as HTMLInputElement)
      .value,
  ).toBe("Explicit synthetic assumption");
});
