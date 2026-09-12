import { StrictMode, useEffect, useState, useRef, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  LayoutDashboard,
  Users,
  SlidersHorizontal,
  UploadCloud,
  MessageSquare,
  LogOut,
  ArrowUpRight,
  ChevronRight,
  CalendarDays,
} from "lucide-react";
import { api, send, setToken, hasSession } from "./api";
import {
  Card,
  Field,
  Notice,
  Metrics,
  Chart,
  Table,
  Evidence,
  Select,
} from "./components";
import type { Row } from "./types";
import { refreshedRange, type DateRange } from "./reporting-range";
import Overview from "./overview";
export { default as Overview } from "./overview";
import "./style.css";
import "./workspace-layout.css";
import Imports from "./imports";
const Budgets = lazy(() => import("./budgets"));
const Revenue = lazy(() => import("./revenue"));
const Clarity = lazy(() => import("./clarity"));
const Appointments = lazy(() => import("./appointments"));
const nav = [
  ["Overview", LayoutDashboard],
  ["Revenue explorer", Activity],
  ["Providers", Users],
  ["Patients & activity", CalendarDays],
  ["Budgets & scenarios", SlidersHorizontal],
  ["Data imports", UploadCloud],
  ["Ask Clarity", MessageSquare],
] as const;
function currentPage() {
  const slug = window.location.hash.slice(1);
  return nav.find(([name]) => encodeURIComponent(name) === slug)?.[0] || "Overview";
}
export function App() {
  const [dataVersion,setDataVersion]=useState(0);
  const availableRange=useRef<DateRange|null>(null),metadataRequest=useRef(0);
  const [budgetDraft,setBudgetDraft]=useState<Row|null>(null);
  const [restoring, setRestoring] = useState(hasSession);
  const [user, setUser] = useState(""),
    [page, updatePage] = useState<string>(currentPage),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [config, setConfig] = useState<Row | null>(null);
  const [start, setStart] = useState(""),
    [end, setEnd] = useState("");
  const currentRange=useRef({start,end});currentRange.current={start,end};
  const currentUser=useRef(user);currentUser.current=user;
  async function refreshFinancialData() {
    setDataVersion(v=>v+1);
    window.dispatchEvent(new Event("clinic-data-updated"));
    if(!config?.analytics.enabled)return;
    const request=++metadataRequest.current,owner=user,selected=currentRange.current;
    try {
      const m=await api('/analytics/metadata');
      if(request!==metadataRequest.current||owner!==currentUser.current)return;
      const today=new Date().toISOString().slice(0,10);
      const next={start:m.first_date||today,end:m.last_date||today};
      // Preserve edits made while this request was in flight as well.
      if(currentRange.current.start===selected.start&&currentRange.current.end===selected.end){
        const range=refreshedRange(selected,availableRange.current,next);setStart(range.start);setEnd(range.end);
      }
      availableRange.current=next;
    } catch(e) {if(request===metadataRequest.current&&owner===currentUser.current)setError(`Import completed, but reporting dates could not refresh: ${(e as Error).message}`);}
  }
  function setPage(name: string) {
    if(!window.dispatchEvent(new Event("clinic-navigation",{cancelable:true}))) return;
    window.location.hash = encodeURIComponent(name);
    updatePage(name);
  }
  useEffect(() => {
    const navigate = () => updatePage(currentPage());
    window.addEventListener("hashchange", navigate);
    if (hasSession()) api("/auth/me").then((u) => setUser(u.username))
      .catch((e) => setError(e.message)).finally(() => setRestoring(false));
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    const expire = () => {
      metadataRequest.current++;availableRange.current=null;
      setBudgetDraft(null);
      setStart("");setEnd("");
      setUser("");
      setConfig(null);
      setError("Your session expired. Sign in again.");
    };
    window.addEventListener("session-expired", expire);
    return () => window.removeEventListener("session-expired", expire);
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    Promise.all(
      ["analytics", "simulations", "ingestion", "questions"].map((p) =>
        api(`/${p}/config`),
      ),
    )
      .then(async ([analytics, simulations, ingestion, questions]) => {
        if (!active) return;
        setConfig({ analytics, simulations, ingestion, questions });
        if (analytics.enabled) {
          const request=++metadataRequest.current;
          const m = await api("/analytics/metadata");
          if (active&&request===metadataRequest.current) {
            setStart(m.first_date || new Date().toISOString().slice(0, 10));
            setEnd(m.last_date || new Date().toISOString().slice(0, 10));
            availableRange.current={start:m.first_date||new Date().toISOString().slice(0,10),end:m.last_date||new Date().toISOString().slice(0,10)};
          }
        } else {
          setStart(new Date().toISOString().slice(0, 10));
          setEnd(new Date().toISOString().slice(0, 10));
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [user]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await send("/auth/login", { username, password });
      setToken(r.access_token);
      setPassword("");
      setUser(username);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (restoring) return <Notice>Restoring your workspace…</Notice>;
  if (!user)
    return (
      <div className="login">
        <div className="login-story">
          <div className="brand">
            <Activity size={27} />
            <b>
              clarity<span>CLINIC INTELLIGENCE</span>
            </b>
          </div>
          <div>
            <span className="eyebrow">A CLEARER PICTURE OF YOUR PRACTICE</span>
            <h1>
              Know your numbers.
              <br />
              Plan what’s next.
            </h1>
            <p>
              Your finances, team, and next big decision.
              <br />
              Connected in one thoughtful workspace.
            </p>
          </div>
          <small>Financial insight. Confident decisions.</small>
        </div>
        <main className="login-form">
          <form onSubmit={login}>
            <span className="eyebrow">YOUR PRACTICE WORKSPACE</span>
            <h2>Welcome back</h2>
            <p>Sign in to see how your clinic is doing.</p>
            {error && <Notice error>{error}</Notice>}
            <Field
              label="Username"
              value={username}
              onChange={setUsername}
              required
            />
            <label className="field">
              <span>Password</span>
              <input
                autoComplete="current-password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Signing in…" : "Sign in to your workspace"}
              <ArrowUpRight size={17} />
            </button>
            <p className="fine">
              Access is managed by your clinic administrator.
            </p>
          </form>
        </main>
      </div>
    );
  const enabled =
    (page === "Overview" || page === "Revenue explorer" || page === "Patients & activity")
      ? config?.analytics.enabled
      : page === "Providers"
        ? config?.analytics.provider_access
        : page === "Budgets & scenarios"
          ? config?.simulations.enabled
          : page === "Data imports"
            ? config?.ingestion.enabled
            : config?.questions.enabled;
  return (
    <div className="app">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <Activity size={27} />
          <b>
            clarity<span>CLINIC INTELLIGENCE</span>
          </b>
        </div>
        <div className="workspace">
          <span className="workspace-icon">C</span>
          <div>
            <b>Clinic workspace</b>
            <small>Financial intelligence</small>
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {nav.map(([name, Icon]) => (
            <button
              key={name}
              className={page === name ? "active" : ""}
              aria-current={page === name ? "page" : undefined}
              onClick={() => setPage(name)}
            >
              <Icon size={19} />
              {name}
              {page === name && (
                <ChevronRight className="nav-arrow" size={15} />
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="mini-note">
            <Activity size={18} />
            <div>
              <b>Built around your practice</b>
              <p>Actuals inform. Assumptions stay visible.</p>
            </div>
          </div>
          <button
            className="user"
            onClick={async () => {
              try {
                await api("/auth/logout", { method: "POST" });
                metadataRequest.current++;availableRange.current=null;
                setToken("");
                setBudgetDraft(null);
                setStart("");setEnd("");
                setUser("");
                setConfig(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <span className="avatar">{user.slice(0, 2).toUpperCase()}</span>
            <span>
              {user}
              <small>Sign out</small>
            </span>
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main-wrap">
        <header>
          <span>
            Workspace <span className="muted">/</span> <b>{page}</b>
          </span>
          <span className="badge">
            {config?.analytics.synthetic_data
              ? "Synthetic test data"
              : "Clinic instance"}
          </span>
        </header>
        <main id="main">
          <div className={`page-heading${["Budgets & scenarios","Ask Clarity"].includes(page)?" compact-heading":""}`}>
            <div>
              <span className="eyebrow">
                {page === "Overview"
                  ? "THE FINANCIAL PULSE OF YOUR PRACTICE"
                  : "YOUR PRACTICE, IN FOCUS"}
              </span>
              <h1>
                {page === "Overview"
                  ? "A clearer view. Better decisions."
                  : page}
              </h1>
              <p>
                {page === "Overview"
                  ? "Understand where you stand, and where you’re headed."
                  : page === "Budgets & scenarios"
                    ? "Build a plan. Explore alternatives. Keep every assumption."
                    : page === "Data imports"
                      ? "Turn your financial exports into useful insight."
                      : page === "Providers"
                        ? "Understand each provider’s contribution, with cost context."
                        : page === "Revenue explorer"
                          ? "Explore collections by insurer, billing code, and reporting period."
                          : page === "Patients & activity"
                            ? "Compare appointment volume and recorded charges over time."
                          : "Ask a financial question. Follow the evidence."}
              </p>
            </div>
            {page === "Overview" && (
              <button
                className="primary"
                onClick={() => setPage("Data imports")}
              >
                <UploadCloud size={17} />
                Import data
              </button>
            )}
          </div>
          {error && <Notice error>{error}</Notice>}
          {!config ? (
            <Notice>Loading your workspace…</Notice>
          ) : !enabled ? (
            <Card title="Access not configured">
              <p>
                Your administrator needs to enable this feature for your
                account.
              </p>
            </Card>
          ) : (
            <>
              <div
                className="date-bar"
                hidden={
                  page === "Budgets & scenarios" || page === "Data imports" || page === "Patients & activity"
                }
              >
                <Field
                  label="From"
                  type="date"
                  value={start}
                  onChange={setStart}
                />
                <Field
                  label="Through"
                  type="date"
                  value={end}
                  onChange={setEnd}
                />
                <span>Selected reporting period</span>
              </div>
              {page === "Overview" && start && end && (
                <Overview start={start} end={end} dataVersion={dataVersion} />
              )}{" "}
              {page === "Revenue explorer" && start && end && <Suspense fallback={<Notice>Loading revenue explorer…</Notice>}><Revenue start={start} end={end} dataVersion={dataVersion} /></Suspense>}
              {page === "Providers" && <Providers start={start} end={end} dataVersion={dataVersion} />}{" "}
              {page === "Patients & activity" && <Suspense fallback={<Notice>Loading appointment activity…</Notice>}><Appointments /></Suspense>}
              {page === "Budgets & scenarios" && (
                <Suspense fallback={<Notice>Loading budgets…</Notice>}>
                  <Budgets
                    draft={budgetDraft}
                    onDraftLoaded={()=>setBudgetDraft(null)}
                    analyticsAccess={config.analytics.enabled}
                    historicalAccess={config.simulations.historical_access}
                    synthetic={config.simulations.synthetic_data}
                  />
                </Suspense>
              )}{" "}
              {page === "Data imports" && <Imports config={config.ingestion} onCompleted={()=>void refreshFinancialData()} />}{" "}
              {page === "Ask Clarity" && (
                <Suspense fallback={<Notice>Loading conversations…</Notice>}><Clarity config={{...config.questions,simulation_access:config.simulations.enabled}} start={start} end={end} onDraft={draft=>{setBudgetDraft(draft);setPage('Budgets & scenarios');}}/></Suspense>
              )}
            </>
          )}
        </main>
        <footer>
          Clarity · Clinic financial intelligence{" "}
          <span>Financial observations and modeled assumptions</span>
        </footer>
      </div>
    </div>
  );
}
function useReport(path: string, dataVersion=0) {
  const [value, setValue] = useState<Row | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setValue(null);
    setError("");
    api(path)
      .then((v) => active && setValue(v))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [path,dataVersion]);
  return { value, error };
}
function Providers({ start, end, dataVersion=0 }: { start: string; end: string; dataVersion?:number }) {
  const { value: d, error } = useReport(
    `/analytics/providers?start=${start}&end=${end}`,dataVersion,
  );
  if (error) return <Notice error>{error}</Notice>;
  if (!d) return <Notice>Loading provider performance…</Notice>;
  return (
    <>
      <Notice>
        Contribution margin is available only where fully loaded costs are
        confirmed.
      </Notice>
      <Card title="Provider contribution">
        <Chart
          bar
          x="label"
          rows={d.providers}
          keys={["revenue", "fully_loaded_cost", "contribution"]}
        />
        <Table
          rows={d.providers}
          columns={[
            "label",
            "revenue",
            "attributed_expense",
            "fully_loaded_cost",
            "contribution",
            "contribution_margin_pct",
            "status",
            "cost_basis",
          ]}
        />
      </Card>
      <Card title="Unattributed activity">
        <Table rows={[d.unattributed]} />
        {d.notes.map((n: string) => (
          <p key={n}>{n}</p>
        ))}
      </Card>
    </>
  );
}
export { default as Questions } from "./clarity";
const root = document.getElementById("root");
if (root) createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
