import { StrictMode, useEffect, useState, lazy, Suspense } from "react";
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
import "./style.css";
import PDFImport from "./pdf-import";
import { financialCSV } from "./financial-csv";
const Budgets = lazy(() => import("./budgets"));
const Revenue = lazy(() => import("./revenue"));
const nav = [
  ["Overview", LayoutDashboard],
  ["Revenue explorer", Activity],
  ["Providers", Users],
  ["Budgets & scenarios", SlidersHorizontal],
  ["Data imports", UploadCloud],
  ["Ask Clarity", MessageSquare],
] as const;
function currentPage() {
  const slug = window.location.hash.slice(1);
  return nav.find(([name]) => encodeURIComponent(name) === slug)?.[0] || "Overview";
}
export function App() {
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
  function setPage(name: string) {
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
          const m = await api("/analytics/metadata");
          if (active) {
            setStart(m.first_date || new Date().toISOString().slice(0, 10));
            setEnd(m.last_date || new Date().toISOString().slice(0, 10));
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
    (page === "Overview" || page === "Revenue explorer")
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
                setToken("");
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
          <div className="page-heading">
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
                  page === "Budgets & scenarios" || page === "Data imports"
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
                <Overview start={start} end={end} />
              )}{" "}
              {page === "Revenue explorer" && start && end && <Suspense fallback={<Notice>Loading revenue explorer…</Notice>}><Revenue start={start} end={end} /></Suspense>}
              {page === "Providers" && <Providers start={start} end={end} />}{" "}
              {page === "Budgets & scenarios" && (
                <Suspense fallback={<Notice>Loading budgets…</Notice>}>
                  <Budgets
                    analyticsAccess={config.analytics.enabled}
                    historicalAccess={config.simulations.historical_access}
                    synthetic={config.simulations.synthetic_data}
                  />
                </Suspense>
              )}{" "}
              {page === "Data imports" && <Imports config={config.ingestion} />}{" "}
              {page === "Ask Clarity" && (
                <Questions config={config.questions} start={start} end={end} />
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
function useReport(path: string) {
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
  }, [path]);
  return { value, error };
}
function Overview({ start, end }: { start: string; end: string }) {
  const { value: d, error } = useReport(
    `/analytics/dashboard?start=${start}&end=${end}`,
  );
  const [frequency, setFrequency] = useState("monthly");
  if (error) return <Notice error>{error}</Notice>;
  if (!d) return <Notice>Loading financial performance…</Notice>;
  const rows = d[frequency];
  return (
    <>
      <Metrics
        currency={d.currency || "USD"}
        items={[
          ["Total revenue", d.summary.revenue, "Recorded collections"],
          ["Total expenses", d.summary.expense, "Recorded clinic costs"],
          ["Net income", d.summary.net, "Revenue less expenses"],
          ["Net margin %", d.summary.margin_pct, "For the selected period"],
        ]}
      />
      <Evidence label="Data coverage and calculation notes" value={d.data_notes} />
      <div className="two-col">
        <Card
          title="Financial performance"
          action={
            <Select
              label="View"
              value={frequency}
              onChange={setFrequency}
              options={["monthly", "weekly"]}
            />
          }
        >
          <p className="muted">Revenue and expenses over time</p>
          <Chart rows={rows} keys={["revenue", "expense"]} />
        </Card>
        <Card title="Cost composition">
          <p className="muted">Recorded expenses by category</p>
          <Chart
            bar
            x="label"
            rows={d.summary.categories
              .filter((c: Row) => c.category_type !== "revenue")
              .map((c: Row) => ({
                ...c,
                label: d.category_labels[c.category_key] || c.category_key,
              }))}
            keys={["amount"]}
          />
        </Card>
      </div>
      <Card title="The details behind the trend">
        <details><summary>About data coverage</summary><p className="fine">
          Recorded activity means at least one transaction exists, not that all
          records have been imported. Date coverage describes the selected date
          range only. Missing data is not zero revenue.
        </p></details>
        <Table
          rows={rows.map((r: Row) => ({
            ...r,
            activity: r.observed ? "Recorded activity" : "No records",
            date_coverage: r.partial ? "Part of week/month selected" : "Entire week/month selected",
          }))}
          columns={[
            "period_start",
            "revenue",
            "expense",
            "net",
            "margin_pct",
            "revenue_growth_pct",
            "expense_growth_pct",
            "activity",
            "date_coverage",
          ]}
        />
      </Card>
      <div className="two-col equal">
        <Card title="Weekly moving averages">
          <Chart
            rows={d.weekly.map((r: Row) => ({
              ...r,
              average_4: r.revenue_ma_4?.value,
              average_12: r.revenue_ma_12?.value,
            }))}
            keys={["average_4", "average_12"]}
          />
          <Evidence
            value={d.weekly.map((r: Row) => ({
              period: r.period_start,
              revenue_4: r.revenue_ma_4,
              revenue_12: r.revenue_ma_12,
              expense_4: r.expense_ma_4,
              expense_12: r.expense_ma_12,
            }))}
            label="Exact averages and window coverage"
          />
        </Card>
        <Card title="Cost structure & volatility">
          <Metrics
            currency={d.currency || "USD"}
            items={[
              ["Fixed costs", d.summary.fixed_cost],
              ["Variable costs", d.summary.variable_cost],
            ]}
          />
          <Table
            rows={[
              {
                metric: "Revenue coefficient of variation",
                ...d.volatility.revenue,
              },
              {
                metric: "Expense coefficient of variation",
                ...d.volatility.expense,
              },
            ]}
          />
          <p className="fine">
            {d.volatility.basis} · Missing weeks: {d.volatility.missing_weeks} ·
            Partial weeks: {d.volatility.partial_weeks}
          </p>
          <Table
            rows={d.summary.categories.map((c: Row) => ({
              ...c,
              category: d.category_labels[c.category_key] || c.category_key,
            }))}
            columns={["category", "amount", "pct_revenue"]}
          />
        </Card>
      </div>
    </>
  );
}
function Providers({ start, end }: { start: string; end: string }) {
  const { value: d, error } = useReport(
    `/analytics/providers?start=${start}&end=${end}`,
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
function Imports({ config }: { config: Row }) {
  const [preparedPDF, setPreparedPDF] = useState<Blob | null>(null);
  const [financialOnly, setFinancialOnly] = useState(false);
  const [projection, setProjection] = useState("");
  const [profile, setProfile] = useState(config.profiles[0] || ""),
    [file, setFile] = useState<File | null>(null),
    [result, setResult] = useState<Row | null>(null),
    [lookup, setLookup] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    setFinancialOnly(false); setProjection(""); setPreparedPDF(null);
  }, [file, profile]);
  useEffect(() => {
    if (
      !result?.upload_id ||
      !["queued", "processing", "pending"].includes(result.status)
    )
      return;
    const timer = setTimeout(
      () =>
        api(`/uploads/${result.upload_id}`)
          .then(setResult)
          .catch((e) => setError(e.message)),
      2000,
    );
    return () => clearTimeout(timer);
  }, [result]);
  async function run(action: () => Promise<Row>) {
    setBusy(true);
    setError("");
    try {
      setResult(await action());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="two-col">
        <Card title="Import financial data">
          <p>CSV, XLSX, or a computer-generated PDF. Up to 10 MiB.</p>
          <Select
            label="Column mapping profile"
            value={profile}
            onChange={setProfile}
            options={config.profiles}
          />
          <label className="dropzone">
            <UploadCloud size={36} />
            <strong>{file?.name || "Choose a financial export"}</strong>
            <span>Browse CSV, XLSX, or PDF files</span>
            <input
              type="file"
              accept=".csv,.xlsx,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <p className="fine">For CSV, only approved financial columns are sent. Other columns are removed locally in your browser; their values are never previewed or uploaded. PDF payment tables are extracted locally using the layout below. XLSX must already contain financial data only.</p>
          {file?.name.toLowerCase().endsWith('.pdf') && config.column_profiles?.[profile] && <PDFImport key={profile+file.name+file.lastModified} file={file} profile={config.column_profiles[profile]} onPrepared={setPreparedPDF} />}
          {preparedPDF && <Notice>Financial PDF rows confirmed. Select Validate &amp; import to submit.</Notice>}
          <label className="check">
            <input type="checkbox" checked={financialOnly} onChange={(e) => setFinancialOnly(e.target.checked)} />
            My approved financial columns contain no patient identifiers. For XLSX, the entire file is financial-only.
          </label>
          <button
            className="primary"
            disabled={busy || !file || !profile || !financialOnly || (file.name.toLowerCase().endsWith(".pdf") && !preparedPDF)}
            onClick={() =>
              run(async () => {
                if (!file) throw Error("Choose a file");
                if (file.size > config.max_bytes)
                  throw Error("File exceeds the 10 MiB limit.");
                let kind = file.name.split(".").pop()?.toLowerCase();
                let body: Blob = file;
                if (kind === 'pdf') {
                  if (!preparedPDF) throw Error('Extract and confirm the PDF financial rows first.');
                  body = preparedPDF; kind = 'csv';
                }
                if (kind === "csv" && !preparedPDF) {
                  const mapping = config.column_profiles?.[profile];
                  if (!mapping) throw Error("Reload the app to load the approved financial mapping.");
                  let text: string;
                  try { text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
                  catch { throw Error("CSV must be UTF-8. Nothing was uploaded."); }
                  const clean = financialCSV(text, mapping);
                  // Keep existing financial-only content hashes stable.
                  body = clean.excludedColumns ? new Blob([clean.csv], { type: "text/csv" }) : file;
                  setProjection(`${clean.excludedColumns} nonfinancial columns removed locally; ${clean.rows} financial rows prepared.`);
                }
                return api(
                  `/uploads/${kind}?profile=${encodeURIComponent(profile)}`,
                  {
                    method: "POST",
                    body,
                    headers: { "Content-Type": "application/octet-stream" },
                  },
                );
              })
            }
          >
            {busy ? "Submitting…" : "Validate & import"}
          </button>
          {projection && <p role="status">{projection}</p>}
        </Card>
        <Card title="A clean foundation">
          <ol className="steps">
            <li>
              <b>Use financial-only data</b>
              <p>CSV columns outside the approved mapping stay in your browser. Patient information must never appear in mapped financial fields.</p>
            </li>
            <li>
              <b>Choose the matching format</b>
              <p>Mapping profiles are configured by your administrator.</p>
            </li>
            <li>
              <b>Review every result</b>
              <p>
                Rejected rows include reasons. Identical files do not create
                duplicate transactions.
              </p>
            </li>
          </ol>
          <p className="fine">
            Different files with overlapping transactions still need review.
            Scanned PDFs are unsupported.
          </p>
        </Card>
      </div>
      {error && <Notice error>{error}</Notice>}
      <Card title="Import status">
        <div className="inline">
          <Field
            label="Reopen an upload by ID"
            value={lookup}
            onChange={setLookup}
          />
          <button
            disabled={busy || !lookup}
            onClick={() =>
              run(() => api(`/uploads/${encodeURIComponent(lookup)}`))
            }
          >
            Look up
          </button>
        </div>
        {result && (
          <>
            <Notice>
              {result.duplicate ? "This file was already submitted. " : ""}
              Status: {result.status} · Upload ID: {result.upload_id}
            </Notice>
            <Table
              rows={[result]}
              columns={[
                "total_rows",
                "rows_accepted",
                "rows_rejected",
                "status",
              ]}
            />
            <Evidence
              value={result}
              label="Full import summary and rejection reasons"
            />
            <button
              disabled={busy}
              onClick={() => run(() => api(`/uploads/${result.upload_id}`))}
            >
              Refresh status
            </button>
            {result.status === "failed" && (
              <button
                disabled={busy}
                onClick={() =>
                  run(() =>
                    api(`/uploads/${result.upload_id}/retry`, {
                      method: "POST",
                    }),
                  )
                }
              >
                Retry import
              </button>
            )}
          </>
        )}
      </Card>
    </>
  );
}
function Questions({
  config,
  start,
  end,
}: {
  config: Row;
  start: string;
  end: string;
}) {
  const [question, setQuestion] = useState(""),
    [scope, setScope] = useState("clinic"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [answer, setAnswer] = useState<Row | null>(null),
    [costs, setCosts] = useState<Row | null>(null);
  useEffect(() => {
    setAnswer(null);
    setCosts(null);
  }, [start, end]);
  return (
    <div className="question-layout">
      <Card title="What would you like to understand?">
        <p className="muted">
          Ask about recorded revenue, expenses, margins, or trends.
        </p>
        <details><summary>Supported questions</summary><p>
          This assistant analyzes recorded transactions. It cannot create, edit,
          or compare saved budgets through chat yet. Use Budget studio for staffing,
          rent, payroll taxes, scenario charts, and editable budget tables.
        </p></details>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            setAnswer(null);
            try {
              setAnswer(
                await send("/questions", {
                  question,
                  start,
                  end,
                  allow_provider_data: scope === "providers",
                  acknowledge_external_processing: true,
                }),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            <span>Your financial question</span>
            <textarea
              required
              maxLength={1000}
              rows={4}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="How did our revenue and expenses change each month?"
            />
          </label>
          <div className="suggestions">
            {(config.demo_questions.length
              ? config.demo_questions
              : [
                  "Show the financial summary",
                  "Show monthly trends",
                  "Show the cost breakdown",
                ]
            )
              .slice(0, 3)
              .map((q: string) => (
                <button type="button" key={q} onClick={() => setQuestion(q)}>
                  {q}
                </button>
              ))}
          </div>
          <p className="fine">{config.disclosure}</p>
          {config.provider_access && (
            <Select label="Question scope" value={scope} onChange={setScope}
              options={[["clinic", "Clinic totals"], ["providers", "Include provider financials"]]} />
          )}
          <p className="fine">Submitting a question agrees to the processing described above.</p>
          <button className="primary" disabled={busy || !start || !end}>
            {busy ? "Reviewing your question…" : "Ask Clarity"}
            <ArrowUpRight size={17} />
          </button>
          {busy && (
            <p role="status">
              Local models may take a few minutes. The database performs all
              calculations.
            </p>
          )}
        </form>
        {error && <Notice error>{error}</Notice>}
        {answer && (
          <div className="answer">
            <span className="eyebrow">
              {answer.cached ? "CACHED ANSWER" : "QUERY RESULT"}
            </span>
            <h3>{answer.interpretation || answer.status}</h3>
            <p>{answer.answer}</p>
            {answer.detail && <p>{answer.detail}</p>}
            <p className="fine">{answer.limitations}</p>
            <h3>Generated SQL</h3>
            <pre>{answer.sql || "No SQL available"}</pre>
            <Evidence
              value={answer.parameters}
              label="Bound query parameters"
            />
            <h3>Database results</h3>
            <Table rows={answer.rows || []} />
          </div>
        )}
      </Card>
      <Card title="Grounded in your numbers">
        <span className="badge">
          {config.provider_name || "Configured provider"}
        </span>
        <p>{config.model}</p>
        <p className="fine">
          {config.requests_per_window} questions per{" "}
          {config.window_seconds / 60} minutes. Cached for{" "}
          {config.cache_seconds / 60} minutes.
        </p>
        <h3>Supported questions</h3>
        <ul>
          {config.supported_questions.map((q: string) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
        {config.cost_report_access && (
          <>
            <button
              onClick={async () => {
                try {
                  setCosts(
                    await api(`/questions/costs?start=${start}&end=${end}`),
                  );
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              View model usage & costs
            </button>
            {costs && (
              <>
                <p className="fine">{costs.note}</p>
                <Table rows={costs.rows} />
              </>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
const root = document.getElementById("root");
if (root) createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
