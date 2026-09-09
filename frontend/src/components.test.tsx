import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Evidence } from "./components";

afterEach(cleanup);

it("renders all nested assumptions as readable fields without JSON", () => {
  const { container } = render(<Evidence value={{
    currency: "USD",
    employee_groups: [{ base_salary: "60000.00", payroll_tax_pct: "10.00" }],
    historical: false,
    end_month: null,
    clinic_costs: [],
  }} />);
  expect(screen.getByText("employee groups")).toBeTruthy();
  expect(screen.getByText("base salary")).toBeTruthy();
  expect(screen.getByText("60000.00")).toBeTruthy();
  expect(screen.getByText("10.00%")).toBeTruthy();
  expect(screen.getByText("No")).toBeTruthy();
  expect(screen.getByText("Not specified")).toBeTruthy();
  expect(screen.getByText("None")).toBeTruthy();
  expect(container.querySelector("pre")).toBeNull();
});

it("renders user text as text, never injected markup", () => {
  const { container } = render(<Evidence value={{ name: '<img src=x onerror="alert(1)">' }} />);
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
});
