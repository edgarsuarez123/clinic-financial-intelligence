import { useEffect, useState } from "react";
import { api, money } from "./api";
import { Card, Chart, Metrics, Notice, Select, Table } from "./components";
import type { Row } from "./types";
import ClinicSelect from "./clinic-select";

const dimensions = [
  ["medical_insurance", "Medical insurance"], ["billing_code", "Billing code"], ["category", "Revenue category"],
] as const;
export default function Revenue({ start, end }: { start: string; end: string }) {
  const [clinic,setClinic]=useState("");
  const [frequency, setFrequency] = useState("month");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [report, setReport] = useState<Row | null>(null);
  const [options, setOptions] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  const [chartType, setChartType] = useState("line");
  const [limit, setLimit] = useState("10");
  const [sort, setSort] = useState("highest");
  useEffect(() => {
    let active = true;
    setReport(null); setError("");
    const query = new URLSearchParams({ start, end, frequency });
    if(clinic) query.set("clinic_location",clinic);
    for (const [key, value] of Object.entries(filters)) if (value !== "all") query.set(key, value.slice(2));
    api(`/analytics/revenue?${query}`).then((value) => { if (active) { setReport(value); setOptions(value.options); } })
      .catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [start, end, frequency, filters, clinic]);
  const currency = report?.currency || "USD";
  const periodLabel = (r: Row) => {
    const [year, month] = r.period_start.split("-").map(Number);
    if (frequency === "quarter") return `Q${Math.ceil(month / 3)} ${year}`;
    if (frequency === "month") return new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, 1)));
    return `Week of ${r.period_start}`;
  };
  return <>
    <Card title="Explore your revenue">
      <p>See recorded revenue by insurer, billing code, and category. Filters apply to every total, chart, and table below.</p>
      <div className="form-grid">
        <ClinicSelect value={clinic} onChange={setClinic} />
        <Select label="Group dates by" value={frequency} onChange={setFrequency}
          options={[["week", "Week (Monday–Sunday)"], ["month", "Calendar month"], ["quarter", "Calendar quarter"]]} />
        {dimensions.map(([key, label]) => <Select key={key} label={label} value={filters[key] || "all"}
          onChange={(value) => setFilters({ ...filters, [key]: value })}
          options={[["all", key === "category" ? "All revenue categories" : key === "medical_insurance" ? "All insurers" : "All billing codes"],
            ...Array.from(new Set([...(options[key] || []).map((v: string) => "v:" + v),
              ...(filters[key] && filters[key] !== "all" ? [filters[key]] : [])])).map((v) => [String(v), String(v).slice(2) || "Not classified"] as [string, string])]} />)}
        <Select label="Trend chart" value={chartType} onChange={setChartType} options={[["line", "Line"], ["bar", "Bars"]]} />
        <Select label="Groups shown in bar charts" value={limit} onChange={setLimit} options={[["5", "Top 5"], ["10", "Top 10"], ["20", "Top 20"]]} />
        <Select label="Breakdown table order" value={sort} onChange={setSort} options={[["highest", "Highest revenue first"], ["lowest", "Lowest revenue first"], ["name", "Alphabetical"]]} />
      </div>
      <button onClick={() => setFilters({})}>Reset filters</button>
      <p className="fine">A missing period means no matching records, not zero revenue. “Not classified” includes older imports and blank insurer/code fields. Revenue is the amount in your import; use collected amounts to analyze collections, not billed charges. This view does not calculate insurer or code profitability.</p>
    </Card>
    {error && <Notice error>{error}</Notice>}
    {!error && !report && <Notice>Loading revenue breakdowns…</Notice>}
    {report && <>
      <Metrics currency={currency} items={[["Revenue matching filters", report.total_revenue, `${report.row_count} imported financial rows`]]} />
      <Card title="Revenue over time">
        <Chart currency={currency} x="period" rows={report.periods.map((r: Row) => ({ ...r, period: periodLabel(r) }))} keys={["revenue"]} bar={chartType === "bar"} />
        <Table rows={report.periods.map((r: Row) => ({
          period: periodLabel(r), from: r.coverage_start, through: r.coverage_end, revenue: r.revenue == null ? "No matching records" : money(r.revenue, currency),
          date_range: r.partial ? "Part of period selected" : "Entire period selected",
        }))} />
      </Card>
      {dimensions.map(([key, label]) => {
        const ranked: Row[] = report.breakdowns[key];
        const ordered = sort === "lowest" ? [...ranked].reverse() : sort === "name" ? [...ranked].sort((a, b) => a.label.localeCompare(b.label)) : ranked;
        return <Card key={key} title={`Revenue by ${label.toLowerCase()}`}>
          <p className="fine">Chart shows the top {limit} groups by revenue; the table includes all {ranked.length} groups. Each breakdown partitions the same total—do not add the breakdowns together.</p>
          <Chart bar horizontal currency={currency} x="label" rows={ranked.slice(0, Number(limit))} keys={["revenue"]} />
          <Table rows={ordered.map((r) => ({ [label]: r.label, revenue: money(r.revenue, currency) }))} />
        </Card>;
      })}
    </>}
  </>;
}
