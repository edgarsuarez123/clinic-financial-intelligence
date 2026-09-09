import { costTrends } from "./cost-trends";
import { useEffect, useState } from "react";
import { Plus, Save, Copy, Play, Trash2 } from "lucide-react";
import { api, send } from "./api";
import {
  Card,
  Field,
  Select,
  Notice,
  Chart,
  Table,
  Metrics,
  Evidence,
} from "./components";
import { newPlan, newStaff, syntheticPlan, type Plan, type Row } from "./types";
export default function Budgets({
  historicalAccess,
  synthetic = false,
}: {
  historicalAccess: boolean;
  synthetic?: boolean;
}) {
  const [plan, setPlan] = useState<Plan>(newPlan),
    [name, setName] = useState("Untitled clinic plan"),
    [saved, setSaved] = useState<Row | null>(null),
    [budgets, setBudgets] = useState<Row[]>([]),
    [hasMore, setHasMore] = useState(false),
    [result, setResult] = useState<Row | null>(null),
    [snapshot, setSnapshot] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [scenario, setScenario] = useState("expected"),
    [comparisons, setComparisons] = useState<Row[]>([]);
  const signature = JSON.stringify(plan),
    dirty = !!snapshot && snapshot !== signature;
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (
        !saved ||
        JSON.stringify(saved.plan) !== signature ||
        saved.name !== name
      ) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [saved, signature, name]);
  async function load(offset = 0) {
    try {
      const r = await api(`/simulations/budgets?offset=${offset}`);
      setBudgets((b) => (offset ? [...b, ...r.budgets] : r.budgets));
      setHasMore(r.has_more);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function change<K extends keyof Plan>(key: K, value: Plan[K]) {
    setPlan((p) => ({ ...p, [key]: value }));
  }
  function staff(i: number, key: string, value: unknown) {
    setPlan((p) => ({
      ...p,
      staff: p.staff.map((s, n) => (n === i ? { ...s, [key]: value } : s)),
    }));
  }
  function cost(i: number, key: string, value: unknown) {
    setPlan((p) => ({
      ...p,
      clinic_costs: p.clinic_costs.map((s, n) =>
        n === i ? { ...s, [key]: value } : s,
      ),
    }));
  }
  async function save() {
    await action(async () => {
      const r = await send(
        saved
          ? `/simulations/budgets/${saved.budget_id}`
          : "/simulations/budgets",
        saved
          ? { name, plan, expected_revision: saved.revision }
          : { name, plan, budget_id: crypto.randomUUID() },
        saved ? "PUT" : "POST",
      );
      setSaved(r);
      setResult(r.result);
      setSnapshot(JSON.stringify(r.plan));
      setNotice(`Saved ${r.name} · revision ${r.revision}`);
      await load();
    });
  }
  function canReplace() {
    return (
      (!saved &&
        plan.staff.length === 0 &&
        plan.clinic_costs.length === 0 &&
        plan.existing_revenue_basis === "") ||
      (saved &&
        JSON.stringify(saved.plan) === signature &&
        saved.name === name) ||
      window.confirm("Discard unsaved edits and open another plan?")
    );
  }
  const [costChart, setCostChart] = useState("line");
  const output = result?.scenarios.find((s: Row) => s.scenario === scenario);
  return (
    <>
      <Card
        title="Your saved plans"
        action={
          <button
            disabled={busy}
            onClick={() => {
              if (canReplace()) {
                setSaved(null);
                setPlan(newPlan());
                setResult(null);
                setSnapshot("");
                setName("Untitled clinic plan");
                setNotice("");
              }
            }}
          >
            <Plus size={16} />
            New plan
          </button>
        }
      >
        <div className="saved-plans">
          {budgets.map((b) => (
            <div
              className={
                saved?.budget_id === b.budget_id
                  ? "saved-plan selected"
                  : "saved-plan"
              }
              key={b.budget_id}
            >
              <button
                disabled={busy}
                onClick={() => {
                  if (canReplace())
                    void action(async () => {
                      const r = await api(
                        `/simulations/budgets/${b.budget_id}`,
                      );
                      setSaved(r);
                      setPlan(r.plan);
                      setName(r.name);
                      setResult(r.result);
                      setSnapshot(JSON.stringify(r.plan));
                    });
                }}
              >
                <strong>{b.name}</strong>
                <span>
                  Revision {b.revision} · {String(b.updated_at).slice(0, 10)}
                </span>
              </button>
              <button
                disabled={
                  busy || comparisons.some((c) => c.budget_id === b.budget_id)
                }
                onClick={() =>
                  action(async () => {
                    const r = await api(`/simulations/budgets/${b.budget_id}`);
                    setComparisons((c) => [...c, r]);
                  })
                }
              >
                Compare
              </button>
            </div>
          ))}
        </div>
        {!budgets.length && (
          <p className="muted">
            Save your first clinic plan below. Your inputs and results will be
            available next time.
          </p>
        )}
        {hasMore && (
          <button onClick={() => load(budgets.length)}>Load more plans</button>
        )}
      </Card>
      {error && <Notice error>{error}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      {synthetic && (
        <button
          onClick={() => {
            if (canReplace()) {
              setPlan(syntheticPlan());
              setSaved(null);
              setName("Synthetic clinic example");
              setResult(null);
              setSnapshot("");
            }
          }}
        >
          Load synthetic example
        </button>
      )}
      <Card title="How projections are calculated">
        <p>Monthly salary = annual salary ÷ 12 × headcount. Benefits and payroll taxes apply your entered percentages to salary. Malpractice and other annual fixed costs are divided by 12.</p>
        <p>Revenue = existing monthly revenue × scenario revenue multiplier + incremental hire revenue × headcount × productivity ramp × revenue multiplier. Each hire’s ramp starts in their scheduled start month.</p>
        <p>Recurring fixed costs use the scenario cost multiplier. Variable costs follow projected hire revenue. Onboarding and startup costs occur once in their scheduled month. Net = revenue − total costs. Cumulative break-even occurs when cumulative net reaches zero; the results also identify whether it stays nonnegative through the horizon.</p>
        <p className="fine">Edit the inputs below, then Run projection or Save plan. These are assumption-based projections; saved comparisons retain their original inputs and results.</p>
      </Card>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy} className="budget-fields">
          <Card title="Plan essentials">
            <div className="form-grid">
              <Field
                label="Plan name"
                required
                value={name}
                onChange={setName}
              />
              <Field
                label="Start date"
                type="date"
                required
                value={plan.start_date}
                onChange={(v) => change("start_date", v)}
              />
              <Field
                label="Months to project"
                type="number"
                min={1}
                max={120}
                value={plan.months}
                onChange={(v) => change("months", Number(v))}
              />
              <Field
                label="Currency (ISO code)"
                value={plan.currency}
                onChange={(v) => change("currency", v.toUpperCase())}
              />
              <Field
                label="Existing monthly clinic revenue"
                type="number"
                min={0}
                value={plan.existing_monthly_revenue}
                onChange={(v) => change("existing_monthly_revenue", v)}
              />
              <Field
                label="Revenue source / assumption"
                required
                value={plan.existing_revenue_basis}
                onChange={(v) => change("existing_revenue_basis", v)}
              />
            </div>
            <p className="fine">
              Existing clinic revenue is counted once. Enter zero explicitly for
              a new clinic. All staff and operating costs below are additive.
            </p>
          </Card>
          <Card
            title="People & payroll"
            action={
              <button
                type="button"
                disabled={plan.staff.length >= 30}
                onClick={() =>
                  change("staff", [...plan.staff, newStaff(plan.months)])
                }
              >
                <Plus size={16} />
                Add employee group
              </button>
            }
          >
            {!plan.staff.length && (
              <p className="empty">
                Add providers, nurses, office managers, and other staff.
              </p>
            )}
            {plan.staff.map((s, i) => (
              <div className="editor-row" key={i}>
                <div className="row-title">
                  <h3>{s.role_type}</h3>
                  <button
                    type="button"
                    aria-label={`Remove employee group ${i + 1}`}
                    onClick={() =>
                      change(
                        "staff",
                        plan.staff.filter((_, n) => n !== i),
                      )
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <Field
                    label="Role"
                    value={s.role_type}
                    onChange={(v) => staff(i, "role_type", v)}
                    required
                  />
                  {[
                    ["Headcount", "headcount"],
                    ["Start month", "start_month"],
                    ["End month", "end_month"],
                  ].map(([l, k]) => (
                    <Field
                      key={k}
                      label={l}
                      type="number"
                      min={1}
                      value={s[k as keyof typeof s] as number}
                      onChange={(v) => staff(i, k, Number(v))}
                    />
                  ))}
                  {[
                    ["Annual salary per person", "annual_salary"],
                    ["Benefits % of salary", "benefits_pct"],
                    ["Payroll tax % of salary", "payroll_tax_pct"],
                    ["Annual malpractice per person", "annual_malpractice"],
                    [
                      "Other annual fixed cost per person",
                      "annual_other_fixed_cost",
                    ],
                    ["Onboarding cost per person", "onboarding_cost"],
                    ["Variable cost % of revenue", "variable_cost_pct"],
                  ].map(([l, k]) => (
                    <Field
                      key={k}
                      label={l}
                      type="number"
                      min={0}
                      value={s[k as keyof typeof s] as string}
                      onChange={(v) => staff(i, k, v)}
                    />
                  ))}
                  <Field
                    label="Cost source / assumption"
                    required
                    value={s.cost_basis}
                    onChange={(v) => staff(i, "cost_basis", v)}
                  />
                  <Select
                    label="Revenue treatment"
                    value={s.revenue_mode}
                    onChange={(v) => {
                      staff(i, "revenue_mode", v);
                      if (v !== "incremental")
                        staff(i, "revenue", {
                          kind: "manual",
                          monthly_revenue: "0",
                          basis: "Revenue not incremental to clinic baseline.",
                          provider_keys: [],
                          start: null,
                          end: null,
                        });
                    }}
                    options={[
                      ["none", "No attributed revenue"],
                      [
                        "included_in_clinic_baseline",
                        "Already in clinic revenue",
                      ],
                      ["incremental", "Additional revenue from new hire"],
                    ]}
                  />
                  {s.revenue_mode === "incremental" && (
                    <>
                      <Select
                        label="Revenue source"
                        value={s.revenue.kind}
                        onChange={(v) =>
                          staff(i, "revenue", {
                            ...s.revenue,
                            kind: v,
                            monthly_revenue: v === "historical" ? null : "0",
                            provider_keys: [],
                            start: null,
                            end: null,
                          })
                        }
                        options={
                          historicalAccess
                            ? ["manual", "historical"]
                            : ["manual"]
                        }
                      />
                      {s.revenue.kind === "manual" ? (
                        <Field
                          label="Full-productivity monthly revenue per person"
                          type="number"
                          min={0}
                          value={s.revenue.monthly_revenue || "0"}
                          onChange={(v) =>
                            staff(i, "revenue", {
                              ...s.revenue,
                              monthly_revenue: v,
                            })
                          }
                        />
                      ) : (
                        <>
                          <Field
                            label="Provider IDs (comma separated)"
                            value={s.revenue.provider_keys.join(",")}
                            onChange={(v) =>
                              staff(i, "revenue", {
                                ...s.revenue,
                                provider_keys: v
                                  .split(",")
                                  .map((k) => k.trim())
                                  .filter(Boolean),
                              })
                            }
                          />
                          <Field
                            label="History from"
                            type="date"
                            value={s.revenue.start || ""}
                            onChange={(v) =>
                              staff(i, "revenue", { ...s.revenue, start: v })
                            }
                          />
                          <Field
                            label="History through"
                            type="date"
                            value={s.revenue.end || ""}
                            onChange={(v) =>
                              staff(i, "revenue", { ...s.revenue, end: v })
                            }
                          />
                        </>
                      )}
                      <Field
                        label="Revenue basis"
                        value={s.revenue.basis}
                        onChange={(v) =>
                          staff(i, "revenue", { ...s.revenue, basis: v })
                        }
                      />
                    </>
                  )}
                </div>
              </div>
            ))}
            <p className="fine">
              Tax percentages are your effective-rate assumptions. Jurisdiction
              rules, wage caps, and tax filing are not calculated.
            </p>
          </Card>
          <Card
            title="Clinic operating & startup costs"
            action={
              <button
                type="button"
                disabled={plan.clinic_costs.length >= 50}
                onClick={() =>
                  change("clinic_costs", [
                    ...plan.clinic_costs,
                    {
                      label: "New cost",
                      monthly_amount: "0",
                      one_time_amount: "0",
                      start_month: 1,
                      end_month: plan.months,
                    },
                  ])
                }
              >
                <Plus size={16} />
                Add cost
              </button>
            }
          >
            <p className="muted">
              Include rent, utilities, software, insurance, equipment, and
              custom costs.
            </p>
            {plan.clinic_costs.map((c, i) => (
              <div className="cost-row" key={i}>
                <Field
                  label="Expense"
                  value={c.label}
                  onChange={(v) => cost(i, "label", v)}
                  required
                />
                <Field
                  label="Monthly amount"
                  type="number"
                  min={0}
                  value={c.monthly_amount}
                  onChange={(v) => cost(i, "monthly_amount", v)}
                />
                <Field
                  label="One-time amount"
                  type="number"
                  min={0}
                  value={c.one_time_amount}
                  onChange={(v) => cost(i, "one_time_amount", v)}
                />
                <Field
                  label="Start month"
                  type="number"
                  min={1}
                  value={c.start_month}
                  onChange={(v) => cost(i, "start_month", Number(v))}
                />
                <Field
                  label="End month"
                  type="number"
                  min={1}
                  value={c.end_month}
                  onChange={(v) => cost(i, "end_month", Number(v))}
                />
                <button
                  type="button"
                  aria-label={`Remove cost ${i + 1}`}
                  onClick={() =>
                    change(
                      "clinic_costs",
                      plan.clinic_costs.filter((_, n) => n !== i),
                    )
                  }
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </Card>
          <Card title="Scenario assumptions">
            <Notice>
              Initial multipliers and ramp steps are illustrative assumptions.
              Review and edit them before relying on a projection.
            </Notice>
            <div className="scenario-editors">
              {plan.scenarios.map((s, i) => (
                <section key={s.name}>
                  <h3 className="capitalize">{s.name}</h3>
                  {[
                    ["Revenue multiplier", "revenue_multiplier"],
                    [
                      "Recurring fixed-cost multiplier",
                      "fixed_cost_multiplier",
                    ],
                    ["Ramp assumption basis", "ramp_basis"],
                  ].map(([l, k]) => (
                    <Field
                      key={k}
                      label={l}
                      type={k === "ramp_basis" ? "text" : "number"}
                      min={0}
                      value={s[k as keyof typeof s] as string}
                      onChange={(v) =>
                        change(
                          "scenarios",
                          plan.scenarios.map((a, n) =>
                            n === i ? { ...a, [k]: v } : a,
                          ),
                        )
                      }
                    />
                  ))}
                  <p className="fine">
                    Productivity fraction by month since hire (1 = 100%).
                  </p>
                  {s.ramp.map((r, j) => (
                    <div className="ramp" key={j}>
                      <Field
                        label="Month"
                        type="number"
                        min={1}
                        max={120}
                        value={r.month}
                        onChange={(v) =>
                          change(
                            "scenarios",
                            plan.scenarios.map((a, n) =>
                              n === i
                                ? {
                                    ...a,
                                    ramp: a.ramp.map((b, m) =>
                                      m === j ? { ...b, month: Number(v) } : b,
                                    ),
                                  }
                                : a,
                            ),
                          )
                        }
                      />
                      <Field
                        label="Productivity"
                        type="number"
                        min={0}
                        value={r.productivity}
                        onChange={(v) =>
                          change(
                            "scenarios",
                            plan.scenarios.map((a, n) =>
                              n === i
                                ? {
                                    ...a,
                                    ramp: a.ramp.map((b, m) =>
                                      m === j ? { ...b, productivity: v } : b,
                                    ),
                                  }
                                : a,
                            ),
                          )
                        }
                      />
                      <button
                        type="button"
                        aria-label={`Remove ${s.name} ramp step ${j + 1}`}
                        onClick={() =>
                          change(
                            "scenarios",
                            plan.scenarios.map((a, n) =>
                              n === i
                                ? {
                                    ...a,
                                    ramp: a.ramp.filter((_, m) => m !== j),
                                  }
                                : a,
                            ),
                          )
                        }
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      change(
                        "scenarios",
                        plan.scenarios.map((a, n) =>
                          n === i
                            ? {
                                ...a,
                                ramp: [
                                  ...a.ramp,
                                  {
                                    month: (a.ramp.at(-1)?.month || 0) + 1,
                                    productivity: "1",
                                  },
                                ],
                              }
                            : a,
                        ),
                      )
                    }
                  >
                    Add ramp step
                  </button>
                </section>
              ))}
            </div>
          </Card>
          <div className="action-bar">
            <span>
              {saved
                ? `Saved revision ${saved.revision}`
                : "New plan · not saved"}
              {dirty ? " · Inputs changed" : ""}
            </span>
            <div>
              <button
                type="button"
                onClick={() =>
                  action(async () => {
                    const r = await send("/simulations/clinic", plan);
                    setResult(r);
                    setSnapshot(signature);
                    setNotice(
                      "Projection updated. Save to keep these inputs and results.",
                    );
                  })
                }
              >
                <Play size={16} />
                Run projection
              </button>
              <button
                type="button"
                onClick={() => {
                  setSaved(null);
                  setName(name + " (copy)");
                  setNotice("Copy created in the editor. Save it to keep it.");
                }}
              >
                <Copy size={16} />
                Duplicate
              </button>
              <button className="primary" type="submit">
                <Save size={16} />
                {busy ? "Working…" : "Save plan"}
              </button>
            </div>
          </div>
        </fieldset>
      </form>
      {result && (
        <>
          <div className="section-heading">
            <div>
              <span className="eyebrow">EXPLORE THE POSSIBILITIES</span>
              <h2>How does your plan hold up?</h2>
            </div>
            <div
              className="tabs"
              role="tablist"
              aria-label="Projection scenario"
            >
              {["pessimistic", "expected", "optimistic"].map((s) => (
                <button
                  key={s}
                  role="tab"
                  aria-selected={scenario === s}
                  onClick={() => setScenario(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          {dirty && (
            <Notice>
              Results below use the previous inputs. Run or save again to update
              them.
            </Notice>
          )}
          {result.ordering_note && <Notice>{result.ordering_note}</Notice>}
          {output && (
            <>
              <Metrics
                currency={output.assumptions.plan.currency}
                items={[
                  ["Projected revenue", output.summary.total_revenue],
                  ["Projected cost", output.summary.total_cost],
                  ["Projected net", output.summary.net],
                  ["Peak modeled deficit", output.summary.peak_modeled_deficit],
                ]}
              />
              <div className="two-col">
                <Card title="Projected monthly performance">
                  <Chart
                    rows={output.periods}
                    x="start"
                    keys={["revenue", "total_cost", "net"]}
                  />
                  <p>
                    First cumulative break-even:{" "}
                    {output.summary.first_break_even
                      ? `month ${output.summary.first_break_even.month}`
                      : "not reached in this horizon"}{" "}
                    · Sustained within horizon:{" "}
                    {output.summary.sustained_break_even_within_horizon
                      ?.month || "not reached"}
                  </p>
                </Card>
                <Card title="Assumptions behind this result">
                  <p>{output.assumptions.scope}</p>
                  <p>{output.assumptions.ramp_rule}</p>
                  <p className="fine">{output.assumptions.cost_rule}</p>
                  <Evidence value={output.assumptions} />
                  <p className="fine">
                    Open the full assumptions to review every rate, cost,
                    schedule, and revenue basis used.
                  </p>
                </Card>
              </div>
              <div className="two-col equal">
                <Card title="Cumulative outlook">
                  <Chart
                    rows={output.periods}
                    x="start"
                    keys={[
                      "cumulative_revenue",
                      "cumulative_cost",
                      "cumulative_net",
                    ]}
                  />
                </Card>
                <Card title="Where the budget goes">
                  <Chart
                    bar
                    rows={output.summary.cost_breakdown}
                    x="label"
                    keys={["amount"]}
                  />
                  <Table rows={output.summary.cost_breakdown} />
                </Card>
              </div>
              <Card title="Cost categories over time">
                <Select label="Cost category chart" value={costChart} onChange={setCostChart} options={[["line","Lines"],["bar","Bars"]]} />
                <Chart currency={output.assumptions.plan.currency} x="start" bar={costChart === "bar"}
                  {...costTrends(output.periods)} />
                <p className="fine">Colors stay consistent between views. Exact payroll and clinic cost details are in the monthly projections below.</p>
              </Card>
              <Card title="Exact monthly projections">
                <Table
                  rows={output.periods}
                  columns={[
                    "month",
                    "start",
                    "revenue",
                    "staff_cost",
                    "clinic_cost",
                    "total_cost",
                    "net",
                    "cumulative_net",
                  ]}
                />
                <Evidence
                  value={output.periods}
                  label="Detailed payroll components and clinic costs"
                />
              </Card>
              <Card title="Sensitivity at a glance">
                <Chart
                  bar
                  x="scenario"
                  rows={result.scenarios.map((s: Row) => ({
                    scenario: s.scenario,
                    ...s.summary,
                  }))}
                  keys={["total_revenue", "total_cost", "net"]}
                />
                <Table
                  rows={result.scenarios.map((s: Row) => ({
                    scenario: s.scenario,
                    ...s.summary,
                  }))}
                  columns={[
                    "scenario",
                    "total_revenue",
                    "total_cost",
                    "net",
                    "peak_modeled_deficit",
                  ]}
                />
              </Card>
            </>
          )}
        </>
      )}
      {comparisons.length > 0 && (
        <Card title="Compare saved plans">
          <Notice>
            Snapshots may use different start dates, horizons, and assumptions.
            Values are shown separately by currency.
          </Notice>
          {Array.from(new Set(comparisons.map((c) => c.plan.currency))).map(
            (currency) => (
              <section key={currency}>
                <h3>{currency} · Expected scenario</h3>
                <Chart
                  bar
                  x="name"
                  rows={comparisons
                    .filter((c) => c.plan.currency === currency)
                    .map((c) => ({
                      name: c.name,
                      ...c.result.scenarios.find(
                        (s: Row) => s.scenario === "expected",
                      ).summary,
                    }))}
                  keys={["total_revenue", "total_cost", "net"]}
                />
                <Table
                  rows={comparisons
                    .filter((c) => c.plan.currency === currency)
                    .map((c) => ({
                      name: c.name,
                      currency,
                      start: c.plan.start_date,
                      months: c.plan.months,
                      ...c.result.scenarios.find(
                        (s: Row) => s.scenario === "expected",
                      ).summary,
                    }))}
                  columns={[
                    "name",
                    "start",
                    "months",
                    "total_revenue",
                    "total_cost",
                    "net",
                  ]}
                />
              </section>
            ),
          )}
          {comparisons.map((c) => (
            <div key={c.budget_id}>
              <Evidence
                label={`${c.name} · revision ${c.revision} · full saved assumptions`}
                value={c.result.scenarios.map((s: Row) => s.assumptions)}
              />
              <button
                onClick={() =>
                  setComparisons((a) =>
                    a.filter((b) => b.budget_id !== c.budget_id),
                  )
                }
              >
                Remove {c.name} from comparison
              </button>
            </div>
          ))}
        </Card>
      )}
    </>
  );
}
