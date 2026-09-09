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
