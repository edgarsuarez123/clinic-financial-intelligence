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
  const [tab,setTab]=useState("Starting financials");
  const [trash,setTrash]=useState<Row[]|null>(null);
  const [baselinePreview,setBaselinePreview]=useState<Row|null>(null);
  const [saveState,setSaveState]=useState("New plan"),[savePaused,setSavePaused]=useState(false);
  const [saveTick,setSaveTick]=useState(0);
  const saving=useRef(false),createId=useRef(crypto.randomUUID()),epoch=useRef(0);
  const invalidInput=useRef<string|null>(null);
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
    [comparisons, setComparisons] = useState<Row[]>([]);
  const signature = JSON.stringify(plan),
    dirty = !!snapshot && snapshot !== signature;
  const latest=useRef({plan,name,saved});latest.current={plan,name,saved};
  function planLocation(id:string|null){const url=new URL(window.location.href);if(id)url.searchParams.set('plan',id);else url.searchParams.delete('plan');window.history.replaceState(null,'',url);}
  useEffect(()=>{if(invalidInput.current&&invalidInput.current!==signature){invalidInput.current=null;setSavePaused(false);}},[signature]);
  useEffect(()=>{
    if(!draft)return;
    epoch.current++;createId.current=crypto.randomUUID();setPlan(structuredClone(draft.plan));setName(draft.name);setSaved(null);setSavePaused(false);setTab('Monthly plan');
    planLocation(null);setResult(null);setSnapshot('');setSaveState('Unsaved changes');
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
      const changed=saving.current || (s.saved ? JSON.stringify(s.saved.plan)!==JSON.stringify(s.plan)||s.saved.name!==s.name : !!s.plan.existing_revenue_basis.trim());
      if(changed&&!window.confirm("Some changes are not saved. Leave this page?")) event.preventDefault();
    };
    window.addEventListener("clinic-navigation",guard);
    return ()=>{window.removeEventListener("clinic-navigation",guard);epoch.current++;};
  },[]);
  useEffect(() => {
    void load();
    const id=new URL(window.location.href).searchParams.get('plan');
    if(id&&!draft){let active=true;const version=epoch.current;setBusy(true);void api(`/simulations/budgets/${id}`).then(r=>{if(active&&version===epoch.current){setSaved(r);setPlan(r.plan);setName(r.name);setResult(r.result);setSnapshot(JSON.stringify(r.plan));setSaveState('Saved');}}).catch(e=>active&&version===epoch.current&&setError(e.message)).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};}
  }, []);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (
        (!saved && (signature!==JSON.stringify(newPlan())||name!=="Untitled clinic plan")) ||
        (saved && (JSON.stringify(saved.plan) !== signature || saved.name !== name))
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
      setSaved(r);
      planLocation(r.budget_id);
      setResult(r.result);
      setSnapshot(JSON.stringify(r.plan));
      if(JSON.stringify(latest.current.plan)===JSON.stringify(current.plan)) setPlan(r.plan);
      setSaveState("Saved");setSavePaused(false);
      await load();
    } catch(e) {
      if(version!==epoch.current) return;
      setError((e as Error).message);setSavePaused(true);
      invalidInput.current=e instanceof ApiError&&e.status===422?JSON.stringify(current.plan):null;
      setSaveState(e instanceof ApiError&&e.status===409?"Conflict · reopen or duplicate":"Not saved · retry");
    } finally {saving.current=false;if(version===epoch.current)setSaveTick(t=>t+1);}
  }
  function canReplace() {
    if(saving.current) {setNotice("Wait for the current save to finish.");return false;}
    return (
      (!saved && signature === JSON.stringify(newPlan()) && name === "Untitled clinic plan") ||
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
      <div className="studio-header"><nav className="tabs studio-tabs" aria-label="Budget workspace">
        {["Starting financials","Monthly plan","Scenarios","Compare"].map(t=><button key={t} type="button" aria-current={tab===t?"page":undefined} onClick={()=>setTab(t)}>{t}</button>)}
      </nav><span role="status" className="save-indicator">{saveState}</span></div>
      <Card
        title="Your saved plans"
        action={
          <button
            disabled={busy}
            onClick={() => {
              if (canReplace()) {
                epoch.current++;createId.current=crypto.randomUUID();setSavePaused(false);setSaveState("New plan");
                planLocation(null);
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
                      planLocation(r.budget_id);
                      epoch.current++;setSavePaused(false);setSaveState("Saved");
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
                  if(saved?.budget_id===b.budget_id){epoch.current++;createId.current=crypto.randomUUID();planLocation(null);setSaved(null);setPlan(newPlan());setResult(null);setName("Untitled clinic plan");setSavePaused(false);setSaveState("New plan");}
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
        <button type="button" onClick={()=>action(async()=>{const r=await api('/simulations/budgets/trash');setTrash(r.budgets);})}>Deleted plans</button>
        {trash&&<div className="trash-list">{!trash.length?<p>No deleted plans.</p>:trash.map(b=><div key={b.budget_id}><span>{b.name}</span><button type="button" onClick={()=>action(async()=>{await send(`/simulations/budgets/${b.budget_id}/restore`,{expected_revision:b.revision});setTrash(t=>t?.filter(p=>p.budget_id!==b.budget_id)||[]);await load();})}>Restore {b.name}</button></div>)}<button type="button" onClick={()=>setTrash(null)}>Close deleted plans</button></div>}
      </Card>
      {error && <Notice error>{error}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      {synthetic && (
        <button
          onClick={() => {
            if (canReplace()) {
              epoch.current++;createId.current=crypto.randomUUID();setSavePaused(false);
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
            epoch.current++;createId.current=crypto.randomUUID();setSavePaused(false);setBaselinePreview(null);
            setPlan(next); setSaved(null); setResult(null); setSnapshot("");
            setName("Current clinic + future changes");
            setNotice("Current revenue and costs loaded. Add future changes below, then run or save your projection.");
        }}>Apply starting financials</button><button type="button" onClick={()=>setBaselinePreview(null)}>Cancel</button></div>}
        </>}
      </Card>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy} className="budget-fields">
          <div hidden={tab!=="Starting financials"}><Card title="Plan essentials">
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
          <RevenueDrivers plan={plan} onChange={setPlan}/>
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
          <MonthlyPlan plan={plan} onChange={setPlan}/>
          </div><div hidden={tab!=="Scenarios"}><Card title="Scenario assumptions">
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
                  if(saving.current){setNotice('Wait for the current save to finish.');return;}
                  epoch.current++;createId.current=crypto.randomUUID();setSavePaused(false);
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
