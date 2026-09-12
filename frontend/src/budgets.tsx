import { costTrends } from "./cost-trends";
import ClinicSelect from "./clinic-select";
import { useEffect, useState, useRef } from "react";
import MonthlyPlan from "./monthly-plan";
import RevenueDrivers from "./revenue-drivers";
import RevenueForecast from "./revenue-forecast";
import { Plus, Save, Copy, Play, Trash2 } from "lucide-react";
import { api, send, ApiError } from "./api";
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
import { newId } from "./uuid";
import "./budget-workspace.css";

type BudgetTab = "Starting financials" | "Monthly plan" | "Scenarios" | "Compare";
type ValidationIssue = { tab: BudgetTab; message: string; field?: string };

const BUDGET_TABS: BudgetTab[] = [
  "Starting financials",
  "Monthly plan",
  "Scenarios",
  "Compare",
];

function nonEmpty(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function decimalInput(value: unknown): boolean {
  if (typeof value !== "string" || !/^\d+(\.\d*)?$/.test(value.trim())) return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1_000_000_000_000;
}

function percentInput(value: unknown, maximum = 100): boolean {
  return decimalInput(value) && Number(value) <= maximum;
}

function integerInput(value: unknown, minimum: number, maximum: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= maximum;
}

function budgetValidation(name: string, plan: Plan): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const add = (tab: BudgetTab, message: string, field?: string) => issues.push({ tab, message, field });

  if (!nonEmpty(name)) add("Starting financials", "Plan name is required.", "name");
  if (!nonEmpty(plan.start_date)) add("Starting financials", "Start date is required.", "plan.start_date");
  if (!integerInput(plan.months, 1, 120)) {
    add("Starting financials", "Months to project must be a whole number from 1 to 120.", "plan.months");
  }
  if (!/^[A-Z]{3}$/.test(plan.currency || "")) {
    add("Starting financials", "Currency must be a three-letter ISO code.", "plan.currency");
  }
  if (!decimalInput(plan.existing_monthly_revenue)) {
    add("Starting financials", "Existing monthly clinic revenue must be a non-negative decimal value.", "plan.existing_monthly_revenue");
  }
  if (!nonEmpty(plan.existing_revenue_basis)) {
    add("Starting financials", "Revenue source / assumption is required.", "plan.existing_revenue_basis");
  }

  plan.staff.forEach((staff, index) => {
    const label = `Employee group ${index + 1}`;
    const prefix = `plan.staff.${index}`;
    if (!nonEmpty(staff.role_type)) add("Monthly plan", `${label}: role is required.`, `${prefix}.role_type`);
    if (!integerInput(staff.headcount, 1, 500)) add("Monthly plan", `${label}: headcount must be a whole number from 1 to 500.`, `${prefix}.headcount`);
    if (!integerInput(staff.start_month, 1, plan.months) || !integerInput(staff.end_month, 1, plan.months) || staff.start_month > staff.end_month) {
      add("Monthly plan", `${label}: start and end months must be whole numbers within the plan horizon and in order.`, `${prefix}.start_month`);
    }
    for (const [field, labelText] of [
      ["annual_salary", "annual salary"],
      ["annual_malpractice", "annual malpractice"],
      ["annual_other_fixed_cost", "other annual fixed cost"],
      ["onboarding_cost", "onboarding cost"],
    ] as const) {
      if (!decimalInput(staff[field])) add("Monthly plan", `${label}: ${labelText} must be a non-negative decimal value.`, `${prefix}.${field}`);
    }
    for (const [field, labelText, maximum] of [
      ["benefits_pct", "benefits", 200],
      ["payroll_tax_pct", "payroll tax", 100],
      ["variable_cost_pct", "variable cost", 100],
    ] as const) {
      if (!percentInput(staff[field], maximum)) add("Monthly plan", `${label}: ${labelText} percentage must be between 0 and ${maximum}.`, `${prefix}.${field}`);
    }
    if (!nonEmpty(staff.cost_basis)) add("Monthly plan", `${label}: cost source / assumption is required.`, `${prefix}.cost_basis`);
    Object.entries(staff.monthly_salary || {}).forEach(([month, value]) => {
      const monthNumber = Number(month);
      if (!integerInput(monthNumber, staff.start_month, staff.end_month) || !decimalInput(value)) {
        add("Monthly plan", `${label}: salary overrides must use non-negative amounts within the employment schedule.`, `${prefix}.monthly_salary.${month}`);
      }
    });
    if (staff.revenue_mode === "incremental") {
      if (staff.revenue.kind === "manual" && !decimalInput(staff.revenue.monthly_revenue || "")) {
        add("Monthly plan", `${label}: enter a non-negative monthly revenue amount or choose historical revenue.`, `${prefix}.revenue.monthly_revenue`);
      }
      if (staff.revenue.kind === "historical") {
        if (!staff.revenue.provider_keys.length) add("Monthly plan", `${label}: add at least one provider ID for historical revenue.`, `${prefix}.revenue.provider_keys`);
        if (!nonEmpty(staff.revenue.start) || !nonEmpty(staff.revenue.end)) {
          add("Monthly plan", `${label}: history from and through dates are required for historical revenue.`, `${prefix}.revenue.start`);
        } else if (typeof staff.revenue.start === "string" && typeof staff.revenue.end === "string" && staff.revenue.start > staff.revenue.end) {
          add("Monthly plan", `${label}: historical revenue dates must be in order.`, `${prefix}.revenue.start`);
        }
      }
      if (!nonEmpty(staff.revenue.basis)) add("Monthly plan", `${label}: revenue basis is required.`, `${prefix}.revenue.basis`);
    }
  });

  plan.clinic_costs.forEach((cost, index) => {
    const label = `Operating cost ${index + 1}`;
    const prefix = `plan.clinic_costs.${index}`;
    if (!nonEmpty(cost.label)) add("Monthly plan", `${label}: expense name is required.`, `${prefix}.label`);
    if (!decimalInput(cost.monthly_amount) || !decimalInput(cost.one_time_amount)) {
      add("Monthly plan", `${label}: monthly and one-time amounts must be non-negative decimal values.`, `${prefix}.monthly_amount`);
    }
    if (!integerInput(cost.start_month, 1, plan.months) || !integerInput(cost.end_month, 1, plan.months) || cost.start_month > cost.end_month) {
      add("Monthly plan", `${label}: start and end months must be whole numbers within the plan horizon and in order.`, `${prefix}.start_month`);
    }
    Object.entries(cost.monthly_amounts || {}).forEach(([month, value]) => {
      const monthNumber = Number(month);
      if (!integerInput(monthNumber, cost.start_month, cost.end_month) || !decimalInput(value)) {
        add("Monthly plan", `${label}: monthly overrides must use non-negative amounts within the expense schedule.`, `${prefix}.monthly_amounts.${month}`);
      }
    });
  });

  if (plan.revenue_mode === "drivers") {
    if (!plan.revenue_drivers?.length) add("Monthly plan", "Add at least one insurance / code revenue driver.", "plan.revenue_drivers");
    plan.revenue_drivers?.forEach((driver, index) => {
      const label = `Revenue driver ${index + 1}`;
      const prefix = `plan.revenue_drivers.${index}`;
      if (!nonEmpty(driver.insurance)) add("Monthly plan", `${label}: insurance is required.`, `${prefix}.insurance`);
      if (!nonEmpty(driver.billing_code)) add("Monthly plan", `${label}: billing code is required.`, `${prefix}.billing_code`);
      if (!decimalInput(driver.monthly_units) || !decimalInput(driver.collected_per_unit)) {
        add("Monthly plan", `${label}: monthly units and collected per unit must be non-negative decimal values.`, `${prefix}.monthly_units`);
      }
      for (const [month, value] of Object.entries(driver.units_by_month || {})) {
        if (!integerInput(Number(month), 1, plan.months) || !decimalInput(value)) {
          add("Monthly plan", `${label}: monthly unit overrides must be non-negative values within the plan horizon.`, `${prefix}.units_by_month.${month}`);
        }
      }
      for (const [month, value] of Object.entries(driver.payment_by_month || {})) {
        if (!integerInput(Number(month), 1, plan.months) || !decimalInput(value)) {
          add("Monthly plan", `${label}: monthly payment overrides must be non-negative values within the plan horizon.`, `${prefix}.payment_by_month.${month}`);
        }
      }
    });
  }

  plan.scenarios.forEach((scenario, index) => {
    const label = `${scenario.name || `Scenario ${index + 1}`} scenario`;
    const prefix = `plan.scenarios.${index}`;
    if (!decimalInput(scenario.revenue_multiplier) || Number(scenario.revenue_multiplier) > 3 ||
      !decimalInput(scenario.fixed_cost_multiplier) || Number(scenario.fixed_cost_multiplier) > 3 ||
      !decimalInput(scenario.volume_multiplier ?? "1") || Number(scenario.volume_multiplier ?? "1") > 3 ||
      !decimalInput(scenario.payment_multiplier ?? "1") || Number(scenario.payment_multiplier ?? "1") > 3) {
      add("Scenarios", `${label}: multipliers must be decimal values from 0 to 3.`, `${prefix}.revenue_multiplier`);
    }
    if (!nonEmpty(scenario.ramp_basis)) add("Scenarios", `${label}: ramp assumption basis is required.`, `${prefix}.ramp_basis`);
    if (!scenario.ramp.length) add("Scenarios", `${label}: add at least one productivity step.`, `${prefix}.ramp`);
    let previousMonth = 0;
    scenario.ramp.forEach((step, stepIndex) => {
      if (!integerInput(step.month, 1, Math.min(120, plan.months)) || step.month <= previousMonth || !percentInput(step.productivity, 1)) {
        add("Scenarios", `${label}: productivity steps must use increasing months and values from 0 to 1.`, `${prefix}.ramp.${stepIndex}`);
      }
      previousMonth = step.month;
    });
  });
  return issues;
}

function ValidationSummary({ issues }: { issues: ValidationIssue[] }) {
  if (!issues.length) return null;
  return (
    <div className="budget-validation" role="status">
      <strong>Complete these inputs before saving</strong>
      <ul>{issues.map((issue, index) => <li key={`${issue.message}-${index}`}>{issue.message}</li>)}</ul>
    </div>
  );
}

function simulationIssues(error: ApiError, fallback: BudgetTab): ValidationIssue[] {
  return error.issues.map((issue) => ({
    tab: issue.field.includes("scenarios")
      ? "Scenarios"
      : issue.field.includes("staff") || issue.field.includes("clinic_costs") || issue.field.includes("revenue_drivers") || issue.field.includes("monthly_salary") || issue.field.includes("monthly_amounts")
        ? "Monthly plan"
        : issue.field.includes("start_date") || issue.field.includes("months") || issue.field.includes("currency") || issue.field.includes("existing_") || issue.field === "name"
          ? "Starting financials"
          : fallback,
    field: issue.field,
    message: `${issue.field.replace(/^plan\.?/, "")} — ${issue.message}`,
  }));
}
export default function Budgets({
  historicalAccess,
  synthetic = false,
  analyticsAccess = false,
  draft = null,
  onDraftLoaded,
}: {
  historicalAccess: boolean;
  synthetic?: boolean;
  analyticsAccess?: boolean;
  draft?: Row|null;
  onDraftLoaded?:()=>void;
}) {
  const [baselineStart, setBaselineStart] = useState("");
  const [tab,setTab]=useState<BudgetTab>("Starting financials");
  const [trash,setTrash]=useState<Row[]|null>(null);
  const [baselinePreview,setBaselinePreview]=useState<Row|null>(null);
  const [saveState,setSaveState]=useState("New plan"),[savePaused,setSavePaused]=useState(false);
  const [saveTick,setSaveTick]=useState(0);
  const saving=useRef(false),createId=useRef(newId()),epoch=useRef(0);
  const invalidInput=useRef<string|null>(null);
  const emptyPlanSignature=useRef(JSON.stringify(newPlan()));
  const projectionRequest=useRef(0);
  const [validation,setValidation]=useState<ValidationIssue[]>([]);
  const [planChooserOpen,setPlanChooserOpen]=useState(true);
  const [staffExpanded,setStaffExpanded]=useState(false);
  const [costsExpanded,setCostsExpanded]=useState(false);
  const [clinic,setClinic]=useState("");
  const [baselineEnd, setBaselineEnd] = useState("");
  useEffect(() => {
    if (!analyticsAccess) return;
    let active = true;
    api("/analytics/metadata").then((m) => {
      if (active) { setBaselineStart(m.first_date || ""); setBaselineEnd(m.last_date || ""); }
    }).catch((e) => active && setError(e.message));
    return () => { active = false; };
  }, [analyticsAccess]);
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
    [comparisons, setComparisons] = useState<Row[]>([]),
    [resultSignature, setResultSignature] = useState("");
  const signature = JSON.stringify(plan),
    inputsChanged = saved
      ? JSON.stringify(saved.plan) !== signature || saved.name !== name
      : signature !== emptyPlanSignature.current || name !== "Untitled clinic plan";
  const dirty = inputsChanged;
  const latest=useRef({plan,name,saved});latest.current={plan,name,saved};
  const issuesFor=(tabName:BudgetTab)=>validation.filter((issue)=>issue.tab===tabName);
  const currentInputSignature=()=>JSON.stringify({plan:latest.current.plan,name:latest.current.name});
  function planLocation(id:string|null){const url=new URL(window.location.href);if(id)url.searchParams.set('plan',id);else url.searchParams.delete('plan');window.history.replaceState(null,'',url);}
  useEffect(()=>{
    if(invalidInput.current&&invalidInput.current!==currentInputSignature()){
      invalidInput.current=null;
      setSavePaused(false);
      setValidation([]);
    }
  },[signature,name]);
  useEffect(()=>{
    if(tab === "Monthly plan" && plan.staff.length) setStaffExpanded(true);
    if(tab === "Monthly plan" && plan.clinic_costs.length) setCostsExpanded(true);
  },[tab,plan.staff.length,plan.clinic_costs.length]);
  useEffect(()=>{
    if(!draft)return;
    epoch.current++;createId.current=newId();setPlan(structuredClone(draft.plan));setName(draft.name);setSaved(null);setSavePaused(false);setTab('Monthly plan');
    planLocation(null);setResult(null);setResultSignature('');setSnapshot('');setValidation([]);setSaveState('Unsaved changes');
    setNotice('Proposed changes opened as a new plan. The original saved plan is unchanged.');onDraftLoaded?.();
  },[draft]);
  useEffect(()=>{
    if(savePaused||busy||saving.current||!plan.existing_revenue_basis.trim()||!name.trim()) return;
    if(saved&&JSON.stringify(saved.plan)===signature&&saved.name===name) return;
    setSaveState("Unsaved changes");
    const timer=setTimeout(()=>{void save();},1200);
    return ()=>clearTimeout(timer);
  },[signature,name,saved,busy,savePaused,saveTick]);
  useEffect(()=>{
    const guard=(event:Event)=>{
      const s=latest.current;
      const changed=saving.current || (s.saved ? JSON.stringify(s.saved.plan)!==JSON.stringify(s.plan)||s.saved.name!==s.name : JSON.stringify(s.plan)!==emptyPlanSignature.current||s.name!=="Untitled clinic plan");
      if(changed&&!window.confirm("Some changes are not saved. Leave this page?")) event.preventDefault();
    };
    window.addEventListener("clinic-navigation",guard);
    return ()=>{window.removeEventListener("clinic-navigation",guard);epoch.current++;};
  },[]);
  useEffect(() => {
    void load();
    const id=new URL(window.location.href).searchParams.get('plan');
    if(id&&!draft){let active=true;const version=epoch.current;setBusy(true);void api(`/simulations/budgets/${id}`).then(r=>{if(active&&version===epoch.current){setSaved(r);setPlan(r.plan);setName(r.name);setResult(r.result);setResultSignature(JSON.stringify(r.plan));setSnapshot(JSON.stringify(r.plan));setValidation([]);setSavePaused(false);setSaveState('Saved');}}).catch(e=>active&&version===epoch.current&&setError(e.message)).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};}
  }, []);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (
        inputsChanged
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
    if(saving.current) return;
    const issues=budgetValidation(latest.current.name,latest.current.plan);
    if(issues.length){
      setValidation(issues);
      setTab(issues[0].tab);
      setSavePaused(true);
      invalidInput.current=currentInputSignature();
      setSaveState("Needs attention");
      setError("Complete the highlighted budget inputs before saving.");
      return;
    }
    setValidation([]);
    saving.current=true;setSaveState("Saving…");setError("");
    const current=latest.current,version=epoch.current;
    try {
      const r = await send(
        current.saved
          ? `/simulations/budgets/${current.saved.budget_id}`
          : "/simulations/budgets",
        current.saved
          ? { name:current.name, plan:current.plan, expected_revision: current.saved.revision }
          : { name:current.name, plan:current.plan, budget_id: createId.current },
        current.saved ? "PUT" : "POST",
      );
      if(version!==epoch.current) return;
      const currentStillOpen=JSON.stringify(latest.current.plan)===JSON.stringify(current.plan)&&latest.current.name===current.name;
      setSaved(r);
      planLocation(r.budget_id);
      setSnapshot(JSON.stringify(r.plan));
      if(currentStillOpen){
        setResult(r.result);
        setResultSignature(JSON.stringify(r.plan));
        setPlan(r.plan);
      } else {
        setNotice("Saved this revision. Your edits made during the save remain in the editor and will be saved next.");
      }
      setSaveState("Saved");setSavePaused(false);
      await load();
    } catch(e) {
      if(version!==epoch.current) return;
      setError((e as Error).message);setSavePaused(true);
      if(e instanceof ApiError&&e.status===422){
        const mapped=simulationIssues(e,tab);
        if(mapped.length){setValidation(mapped);setTab(mapped[0].tab);}
        invalidInput.current=JSON.stringify({plan:current.plan,name:current.name});
      } else invalidInput.current=null;
      setSaveState(e instanceof ApiError&&e.status===409?"Conflict · reopen or duplicate":"Not saved · retry");
    } finally {saving.current=false;if(version===epoch.current)setSaveTick(t=>t+1);}
  }
  function canReplace() {
    if(saving.current) {setNotice("Wait for the current save to finish.");return false;}
    return (
      (!saved && signature === emptyPlanSignature.current && name === "Untitled clinic plan") ||
      (saved &&
        JSON.stringify(saved.plan) === signature &&
        saved.name === name) ||
      window.confirm("Discard unsaved edits and open another plan?")
    );
  }
  async function runProjection() {
    const request=++projectionRequest.current;
    const version=epoch.current;
    const requestedPlan=JSON.stringify(latest.current.plan);
    await action(async()=>{
      const r=await send("/simulations/clinic",latest.current.plan);
      if(request!==projectionRequest.current||version!==epoch.current) return;
      if(JSON.stringify(latest.current.plan)!==requestedPlan){
        setNotice("Projection finished for earlier inputs. Run again to refresh the displayed results.");
        return;
      }
      setResult(r);
      setResultSignature(requestedPlan);
      setSnapshot(requestedPlan);
      setNotice("Projection updated. Save to keep these inputs and results.");
    });
  }
  const [costChart, setCostChart] = useState("line");
  const output = result?.scenarios?.find((s: Row) => s.scenario === scenario);
  const resultsStale=!!result && !!resultSignature && resultSignature!==signature;
  return (
    <div className="budget-workspace">
      <div className="studio-header"><nav className="tabs studio-tabs" aria-label="Budget workspace">
        {BUDGET_TABS.map(t=><button key={t} type="button" aria-current={tab===t?"page":undefined} onClick={()=>setTab(t)}>{t}</button>)}
      </nav><span role="status" className="save-indicator">{saveState}</span></div>
      <div className="budget-plan-chooser">
      <Card
        title="Your saved plans"
        action={
          <button
            disabled={busy}
            onClick={() => {
              if (canReplace()) {
                epoch.current++;createId.current=newId();setSavePaused(false);setSaveState("New plan");setValidation([]);
                planLocation(null);
                setSaved(null);
                setPlan(newPlan());
                setResult(null);
                setResultSignature("");
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
        <details className="plan-chooser" open={planChooserOpen} onToggle={(event)=>setPlanChooserOpen(event.currentTarget.open)}>
          <summary>
            <span>Choose a saved plan</span>
            <span className="plan-chooser-count">{budgets.length ? `${budgets.length}${hasMore ? "+" : ""} available` : "None saved yet"}</span>
          </summary>
          <div className="plan-chooser-content">
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
                      planLocation(r.budget_id);
                      epoch.current++;setSavePaused(false);setSaveState("Saved");
                      setPlan(r.plan);
                      setName(r.name);
                      setResult(r.result);
                      setResultSignature(JSON.stringify(r.plan));
                      setSnapshot(JSON.stringify(r.plan));
                      setValidation([]);
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
                    setTab("Compare");
                  })
                }
              >
                Compare
              </button>
              <button type="button" aria-label={`Delete ${b.name}`} disabled={busy} onClick={()=>{
                if(!canReplace()||!window.confirm(`Move “${b.name}” to deleted plans? You can restore it.`)) return;
                void action(async()=>{
                  await send(`/simulations/budgets/${b.budget_id}`,{expected_revision:b.revision},"DELETE");
                  if(saved?.budget_id===b.budget_id){epoch.current++;createId.current=newId();planLocation(null);setSaved(null);setPlan(newPlan());setResult(null);setResultSignature("");setName("Untitled clinic plan");setSavePaused(false);setSaveState("New plan");setValidation([]);}
                  setComparisons(c=>c.filter(p=>p.budget_id!==b.budget_id));await load();setNotice("Plan moved to deleted plans. It can be restored.");
                });
              }}><Trash2 size={16}/></button>
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
          </div>
        </details>
        <div className="plan-chooser-footer">
        <button type="button" onClick={()=>action(async()=>{const r=await api('/simulations/budgets/trash');setTrash(r.budgets);})}>Deleted plans</button>
        </div>
        {trash&&<div className="trash-list">{!trash.length?<p>No deleted plans.</p>:trash.map(b=><div key={b.budget_id}><span>{b.name}</span><button type="button" onClick={()=>action(async()=>{await send(`/simulations/budgets/${b.budget_id}/restore`,{expected_revision:b.revision});setTrash(t=>t?.filter(p=>p.budget_id!==b.budget_id)||[]);await load();})}>Restore {b.name}</button></div>)}<button type="button" onClick={()=>setTrash(null)}>Close deleted plans</button></div>}
      </Card>
      </div>
      {error && <Notice error>{error}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      {synthetic && (
        <button
          onClick={() => {
            if (canReplace()) {
              epoch.current++;createId.current=newId();setSavePaused(false);
              setPlan(syntheticPlan());
              setSaved(null);
              setName("Synthetic clinic example");
              setResult(null);
              setResultSignature("");
              setSnapshot("");
              setValidation([]);
              setSaveState("Unsaved changes");
            }
          }}
        >
          Load synthetic example
        </button>
      )}
      {tab==="Starting financials"&&<Card title="Start with current financials">
        {!analyticsAccess ? <Notice>Current financials require analytics access for your account.</Notice> : <>
        <div className="form-grid">
          <ClinicSelect value={clinic} onChange={setClinic} />
          <Field label="Baseline from" type="date" value={baselineStart} onChange={setBaselineStart} />
          <Field label="Baseline through" type="date" value={baselineEnd} onChange={setBaselineEnd} />
        </div>
        <p className="fine">Uses complete months. Recorded payroll and overhead are included; add only new costs or hires.</p>
        <button disabled={busy || !baselineStart || !baselineEnd} onClick={() => {
          if (!canReplace()) return;
          void action(async () => {
            const b = await api(`/simulations/baseline?start=${baselineStart}&end=${baselineEnd}${clinic ? `&clinic_location=${encodeURIComponent(clinic)}` : ""}`);
            setBaselinePreview({...b,start:baselineStart,end:baselineEnd,clinic_location:clinic||null});
          });
        }}>Use current financials</button>
        {baselinePreview&&<div className="baseline-review"><h3>Review starting financials</h3><Metrics currency={baselinePreview.currency} items={[["Monthly revenue",baselinePreview.existing_monthly_revenue]]}/><Table rows={baselinePreview.costs}/>
        <p className="fine">This replaces the editor with the recorded monthly averages, including existing payroll. Saved alternatives stay unchanged.</p>
        <button type="button" className="primary" onClick={()=>{
            if(!canReplace()) return;
            const b=baselinePreview;const next = newPlan();
            const endDate = new Date(`${b.end}T00:00:00Z`);
            endDate.setUTCDate(endDate.getUTCDate() + 1);
            next.start_date = endDate.toISOString().slice(0, 10);
            next.currency = b.currency;
            next.existing_monthly_revenue = b.existing_monthly_revenue;
            next.existing_revenue_basis = b.basis;
            next.clinic_costs = b.costs.map((c: Row) => ({ ...c, one_time_amount: "0", start_month: 1, end_month: next.months }));
            next.baseline={start:b.start,end:b.end,clinic_location:b.clinic_location,revenue:b.existing_monthly_revenue,costs:structuredClone(next.clinic_costs)};
            epoch.current++;createId.current=newId();setSavePaused(false);setBaselinePreview(null);
            setPlan(next); setSaved(null); setResult(null); setResultSignature(""); setSnapshot("");
            setName("Current clinic + future changes");
            setNotice("Current revenue and costs loaded. Add future changes below, then run or save your projection.");
        }}>Apply starting financials</button><button type="button" onClick={()=>setBaselinePreview(null)}>Cancel</button></div>}
        </>}
      </Card>}
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy} className="budget-fields">
          <div hidden={tab!=="Starting financials"}><Card title="Plan essentials">
            <ValidationSummary issues={issuesFor("Starting financials")} />
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
          </Card></div>
          <div hidden={tab!=="Monthly plan"}>
          <ValidationSummary issues={issuesFor("Monthly plan")} />
          <RevenueDrivers plan={plan} onChange={setPlan}/>
          <Card
            title="People & payroll"
            action={
              <button
                type="button"
                disabled={plan.staff.length >= 30}
                onClick={() => {
                  setStaffExpanded(true);
                  change("staff", [...plan.staff, newStaff(plan.months)]);
                }}
              >
                <Plus size={16} />
                Add employee group
              </button>
            }
          >
            <details className="budget-disclosure" open={staffExpanded} onToggle={(event)=>setStaffExpanded(event.currentTarget.open)}>
              <summary>
                <span className="disclosure-summary"><span>Employee groups</span><span className="disclosure-meta">{plan.staff.length ? `${plan.staff.length} configured` : "None added"}</span></span>
              </summary>
            <ValidationSummary issues={issuesFor("Monthly plan").filter((issue)=>issue.message.includes("Employee group"))} />
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
                            ? [["manual", "Manual monthly assumption"], ["historical", "Historical provider collections"]]
                            : [["manual", "Manual monthly assumption"]]
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
            </details>
          </Card>
          <Card
            title="Clinic operating & startup costs"
            action={
              <button
                type="button"
                disabled={plan.clinic_costs.length >= 50}
                onClick={() => {
                  setCostsExpanded(true);
                  change("clinic_costs", [
                    ...plan.clinic_costs,
                    {
                      label: "New cost",
                      monthly_amount: "0",
                      one_time_amount: "0",
                      start_month: 1,
                      end_month: plan.months,
                    },
                  ]);
                }}
              >
                <Plus size={16} />
                Add cost
              </button>
            }
          >
            <details className="budget-disclosure" open={costsExpanded} onToggle={(event)=>setCostsExpanded(event.currentTarget.open)}>
              <summary>
                <span className="disclosure-summary"><span>Operating and startup costs</span><span className="disclosure-meta">{plan.clinic_costs.length ? `${plan.clinic_costs.length} configured` : "None added"}</span></span>
              </summary>
            <ValidationSummary issues={issuesFor("Monthly plan").filter((issue)=>issue.message.includes("Operating cost"))} />
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
            </details>
          </Card>
          <MonthlyPlan plan={plan} onChange={setPlan}/>
          </div><div hidden={tab!=="Scenarios"}><Card title="Scenario assumptions">
            <ValidationSummary issues={issuesFor("Scenarios")} />
            <p className="fine">Sensitivity assumptions for this saved plan. Duplicate the plan for an independently editable alternative.</p>
            <div className="scenario-editors">
              {plan.scenarios.map((s, i) => (
                <section key={s.name}>
                  <h3 className="capitalize">{s.name}</h3>
                  {[
                    ["Revenue multiplier", "revenue_multiplier"],
                    ["Volume multiplier", "volume_multiplier"],
                    ["Collected payment multiplier", "payment_multiplier"],
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
                      value={(s[k as keyof typeof s] ?? "1") as string}
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
          </div><div className="action-bar">
            <span>
              {saved
                ? `Saved revision ${saved.revision}`
                : "New plan · not saved"}
              {dirty ? " · Inputs changed" : ""}
            </span>
            <div>
              <button
                type="button"
                onClick={() => void runProjection()}
              >
                <Play size={16} />
                Run projection
              </button>
              <button
                type="button"
                onClick={() => {
                  if(saving.current){setNotice('Wait for the current save to finish.');return;}
                  epoch.current++;createId.current=newId();setSavePaused(false);
                  planLocation(null);
                  setSaved(null);
                  setName(name + " (copy)");
                  setNotice("Independent copy created. Valid changes save automatically.");
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
      {tab==="Compare"&&analyticsAccess&&<RevenueForecast defaultStart={baselineStart} defaultEnd={baselineEnd} defaultClinic={clinic}/>}
      {tab==="Compare"&&result && (
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
          {resultsStale && (
            <Notice>
              Results below use previous inputs. Run or save again to update them.
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
                  ["Net margin %", output.summary.margin_pct],
                ]}
              />
              {output.baseline_comparison&&<Metrics currency={plan.currency} items={[["Net change vs starting financials",output.baseline_comparison.projected_net_change]]}/>}
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
                <Card title="Plan basis">
                  <p>{plan.baseline?`Recorded baseline: ${plan.baseline.start} – ${plan.baseline.end} · ${plan.baseline.clinic_location||'All clinics'}`:'Manual assumptions'}</p>
                  <p>Peak modeled deficit: {output.summary.peak_modeled_deficit} {plan.currency}</p>
                  <Evidence value={result.input_plan||output.assumptions} label="View assumptions"/>
                  {!!output.hiring_results?.length&&<><h3>Incremental hiring payback</h3><Table rows={output.hiring_results.map((h:Row)=>({role:h.role_type,net:h.net,break_even_month:h.first_break_even?h.start_month+h.first_break_even.month-1:'Not reached'}))}/></>}
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
                <Chart currency={output.assumptions.plan.currency} x="start" bar={costChart === "bar"} stacked={costChart === "bar"}
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
                    "margin_pct",
                    ...(output.baseline_comparison?["net_change"]:[]),
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
                  rows={(result.scenarios || []).map((s: Row) => ({
                    scenario: s.scenario,
                    ...s.summary,
                  }))}
                  keys={["total_revenue", "total_cost", "net"]}
                />
                <Table
                  rows={(result.scenarios || []).map((s: Row) => ({
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
      {tab==="Compare"&&comparisons.length > 0 && (
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
                      ...(c.result?.scenarios?.find(
                        (s: Row) => s.scenario === "expected",
                      )?.summary || {}),
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
                      ...(c.result?.scenarios?.find(
                        (s: Row) => s.scenario === "expected",
                      )?.summary || {}),
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
                value={(c.result?.scenarios || []).map((s: Row) => s.assumptions)}
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
    </div>
  );
}
