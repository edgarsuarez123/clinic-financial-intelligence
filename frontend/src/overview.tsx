import { useEffect, useState } from "react";
import { api, money } from "./api";
import { Card, Chart, Metrics, Notice, Select, Table } from "./components";
import type { Row } from "./types";
import ClinicSelect from "./clinic-select";

/**
 * Load one report while ignoring responses from an older date/filter request.
 * The revision is deliberately a dependency rather than a query parameter: a
 * completed import invalidates the report without changing the selected range.
 */
function useReport(path: string, dataVersion = 0) {
  const [value, setValue] = useState<Row | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setValue(null);
    setError("");
    api(path)
      .then((next) => active && setValue(next))
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, [path, dataVersion]);

  return { value, error };
}

type OverviewProps = {
  start: string;
  end: string;
  /** Increment after a completed import to refresh mounted reports. */
  dataVersion?: number;
};

function variationStatus(reason: unknown): string | null {
  if (reason === "fewer_than_two_periods") return "At least two observed weeks are needed";
  if (reason === "zero_mean") return "Unavailable when the average is zero";
  return reason == null ? null : String(reason);
}

export default function Overview({ start, end, dataVersion = 0 }: OverviewProps) {
  const [clinic, setClinic] = useState("");
  const dashboardPath = `/analytics/dashboard?start=${start}&end=${end}${
    clinic ? `&clinic_location=${encodeURIComponent(clinic)}` : ""
  }`;
  const { value: d, error } = useReport(dashboardPath, dataVersion);
  const { value: locations, error: locationError } = useReport(
    `/analytics/locations?start=${start}&end=${end}`,
    dataVersion,
  );
  const [frequency, setFrequency] = useState("monthly");

  if (error)
    return (
      <>
        <ClinicSelect key={dataVersion} value={clinic} onChange={setClinic} />
        <Notice error>{error}</Notice>
      </>
    );
  if (!d)
    return (
      <>
        <ClinicSelect key={dataVersion} value={clinic} onChange={setClinic} />
        <Notice>Loading financial performance…</Notice>
      </>
    );

  const currency = d.currency || "USD";
  const summary = d.summary || {};
  const labels = d.category_labels || {};
  const rows: Row[] = Array.isArray(d[frequency]) ? d[frequency] : [];
  const weekly: Row[] = Array.isArray(d.weekly) ? d.weekly : [];
  const categories: Row[] = Array.isArray(summary.categories)
    ? summary.categories
    : [];
  const volatility = d.volatility || {};
  const revenueVariation = volatility.revenue || {};
  const expenseVariation = volatility.expense || {};

  const averageRows = weekly.map((row: Row) => ({
    Week: row.period_start ? `Week of ${row.period_start}` : "Unknown week",
    "4-week average":
      row.revenue_ma_4?.value == null
        ? null
        : money(row.revenue_ma_4.value, currency),
    "12-week average":
      row.revenue_ma_12?.value == null
        ? null
        : money(row.revenue_ma_12.value, currency),
  }));

  const variationRows = [
    {
      Measure: "Revenue",
      "Week-to-week variation": revenueVariation.value,
      "Observed weeks": revenueVariation.samples,
      Status: variationStatus(revenueVariation.reason),
    },
    {
      Measure: "Expenses",
      "Week-to-week variation": expenseVariation.value,
      "Observed weeks": expenseVariation.samples,
      Status: variationStatus(expenseVariation.reason),
    },
  ];

  return (
    <>
      <ClinicSelect key={dataVersion} value={clinic} onChange={setClinic} />
      <Metrics
        currency={currency}
        items={[
          ["Total revenue", summary.revenue, "Recorded collections"],
          ["Total expenses", summary.expense, "Recorded clinic costs"],
          ["Net income", summary.net, "Revenue less expenses"],
          ["Net margin %", summary.margin_pct, "For the selected period"],
        ]}
      />
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
          <Chart rows={rows} keys={["revenue", "expense"]} currency={currency} />
        </Card>
        <Card title="Where expenses go">
          <p className="muted">Recorded expenses by category</p>
          <Chart
            bar
            x="label"
            rows={categories
              .filter((category: Row) => category.category_type !== "revenue")
              .map((category: Row) => ({
                ...category,
                label:
                  labels[category.category_key] || category.category_key,
              }))}
            keys={["amount"]}
            currency={currency}
          />
        </Card>
      </div>
      <Card title="The details behind the trend">
        <Table
          rows={rows}
          columns={[
            "period_start",
            "revenue",
            "expense",
            "net",
            "margin_pct",
            "revenue_growth_pct",
            "expense_growth_pct",
          ]}
        />
      </Card>
      {!clinic && locations && Array.isArray(locations.rows) && locations.rows.length > 0 && (
        <Card title="Revenue & expenses by clinic">
          <Table
            rows={locations.rows}
            columns={["clinic_location", "currency", "revenue", "expense", "net"]}
          />
        </Card>
      )}
      {locationError && <Notice error>{locationError}</Notice>}
      <div className="two-col equal">
        <Card title="Weekly revenue averages">
          <Chart
            currency={currency}
            rows={weekly.map((row: Row) => ({
              ...row,
              "4-week average": row.revenue_ma_4?.value,
              "12-week average": row.revenue_ma_12?.value,
            }))}
            keys={["4-week average", "12-week average"]}
          />
          <Table
            rows={averageRows}
            columns={["Week", "4-week average", "12-week average"]}
          />
        </Card>
        <Card title="Costs and week-to-week variation">
          <Metrics
            currency={currency}
            items={[
              ["Fixed costs", summary.fixed_cost],
              ["Variable costs", summary.variable_cost],
            ]}
          />
          <Table
            rows={variationRows}
            columns={[
              "Measure",
              "Week-to-week variation",
              "Observed weeks",
            ]}
          />
         
          <Table
            rows={categories.map((category: Row) => ({
              ...category,
              category:
                labels[category.category_key] || category.category_key,
            }))}
            columns={["category", "amount", "pct_revenue"]}
          />
        </Card>
      </div>
    </>
  );
}
