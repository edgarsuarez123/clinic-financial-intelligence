export type Row = Record<string, any>;
export type Revenue = {
  kind: "manual" | "historical";
  monthly_revenue: string | null;
  basis: string;
  provider_keys: string[];
  start: string | null;
  end: string | null;
};
export type Staff = {
  role_type: string;
  headcount: number;
  start_month: number;
  end_month: number;
  revenue_mode: string;
  annual_salary: string;
  benefits_pct: string;
  payroll_tax_pct: string;
  annual_malpractice: string;
  annual_other_fixed_cost: string;
  onboarding_cost: string;
  variable_cost_pct: string;
  cost_basis: string;
  revenue: Revenue;
};
export type Cost = {
  label: string;
  monthly_amount: string;
  one_time_amount: string;
  start_month: number;
  end_month: number;
};
export type Scenario = {
  name: string;
  revenue_multiplier: string;
  fixed_cost_multiplier: string;
  ramp: { month: number; productivity: string }[];
  ramp_basis: string;
};
export type Plan = {
  start_date: string;
  months: number;
  currency: string;
  existing_monthly_revenue: string;
  existing_revenue_basis: string;
  staff: Staff[];
  clinic_costs: Cost[];
  scenarios: Scenario[];
};
export const newPlan = (): Plan => ({
  start_date: new Date().toISOString().slice(0, 10),
  months: 12,
  currency: "USD",
  existing_monthly_revenue: "0",
  existing_revenue_basis: "",
  staff: [],
  clinic_costs: [],
  scenarios: ["pessimistic", "expected", "optimistic"].map((name) => ({
    name,
    revenue_multiplier:
      name === "pessimistic" ? "0.8" : name === "optimistic" ? "1.2" : "1",
    fixed_cost_multiplier: "1",
    ramp: [
      { month: 1, productivity: "0.5" },
      { month: 4, productivity: "0.75" },
      { month: 7, productivity: "1" },
    ],
    ramp_basis: "Illustrative assumption; not calibrated to hiring history.",
  })),
});
export const newStaff = (months: number): Staff => ({
  role_type: "New employee group",
  headcount: 1,
  start_month: 1,
  end_month: months,
  revenue_mode: "none",
  annual_salary: "0",
  benefits_pct: "0",
  payroll_tax_pct: "0",
  annual_malpractice: "0",
  annual_other_fixed_cost: "0",
  onboarding_cost: "0",
  variable_cost_pct: "0",
  cost_basis: "",
  revenue: {
    kind: "manual",
    monthly_revenue: "0",
    basis: "No incremental revenue assumed.",
    provider_keys: [],
    start: null,
    end: null,
  },
});

export function syntheticPlan(): Plan {
  const plan = newPlan();
  plan.existing_monthly_revenue = "25000";
  plan.existing_revenue_basis =
    "Synthetic example only: assumed existing collections of 25000 per month.";
  const employee = newStaff(12);
  employee.role_type = "Office team";
  employee.headcount = 2;
  employee.annual_salary = "60000";
  employee.benefits_pct = "20";
  employee.payroll_tax_pct = "10";
  employee.cost_basis =
    "Synthetic worked example: 20% benefits and 10% effective payroll tax, not jurisdiction rates.";
  plan.staff = [employee];
  plan.clinic_costs = [
    {
      label: "Rent",
      monthly_amount: "3000",
      one_time_amount: "0",
      start_month: 1,
      end_month: 12,
    },
    {
      label: "Utilities",
      monthly_amount: "400",
      one_time_amount: "0",
      start_month: 1,
      end_month: 12,
    },
    {
      label: "Software",
      monthly_amount: "300",
      one_time_amount: "0",
      start_month: 1,
      end_month: 12,
    },
  ];
  return plan;
}
