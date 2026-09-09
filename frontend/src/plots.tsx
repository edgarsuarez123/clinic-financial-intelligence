import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import type { Row } from "./types";
import { money, percent, displayNumber } from "./api";
const colors = ["#167b70", "#b85b23", "#5767b0", "#a34d79", "#927016", "#287ca3", "#774da6", "#6b7c32", "#b84242", "#476477"];
export function categoryColor(label: string) {
  let hash = 0;
  for (const character of label) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  const known = ["Staff: salary", "Staff: benefits", "Staff: payroll taxes", "Staff: malpractice", "Staff: other fixed costs", "Staff: variable costs", "Staff: onboarding", "Clinic: Rent", "Clinic: Utilities", "Clinic: Software"].indexOf(label);
  if (known >= 0) return colors[known];
  return "#" + [0,8,16].map(shift => (40 + ((hash >>> shift) % 120)).toString(16).padStart(2,"0")).join("");
}
const metricColor = (key: string) => /^(cumulative_|total_)?revenue$/.test(key) ? colors[0] : /^(cumulative_|total_)?(cost|expense)$/.test(key) ? colors[1] : /^(cumulative_)?net$/.test(key) ? colors[2] : categoryColor(key);
export default function Plot({
  rows,
  keys,
  x = "period_start",
  bar = false,
  horizontal = false,
  currency,
}: {
  rows: Row[];
  keys: string[];
  x?: string;
  bar?: boolean;
  horizontal?: boolean;
  currency?: string;
}) {
  const [overrides, setOverrides] = useState<Record<string,string>>({});
  const categorical = bar && keys.length === 1 && !["period_start","period","start"].includes(x);
  const color = (label:string) => overrides[label] || (categorical ? categoryColor(label) : metricColor(label));
  const labels = categorical ? Array.from(new Set(rows.map(row => String(row[x])))) : keys;
  const data: Row[] = rows.map((r) => ({
    ...r,
    exact_values: r,
    ...Object.fromEntries(
      keys.map((k) => [k, r[k] == null ? null : Number(r[k])]),
    ),
  }));
  const parts = [
    <CartesianGrid key="grid" vertical={false} stroke="#e9eeeb" />,
    <XAxis
      key="x"
      dataKey={horizontal ? undefined : x}
      type={horizontal ? "number" : "category"}
      tickLine={false}
      axisLine={false}
      tick={{ fontSize: 11, fill: "#62736e" }}
      minTickGap={25}
    />,
    <YAxis
      key="y"
      width={horizontal ? 155 : 65}
      type={horizontal ? "category" : "number"}
      dataKey={horizontal ? x : undefined}
      tickLine={false}
      axisLine={false}
      tick={{ fontSize: 11, fill: "#62736e" }}
      tickFormatter={(v) => horizontal ? (String(v).length > 23 ? String(v).slice(0, 22) + "…" : String(v)) : (Math.abs(v) >= 1000 ? `${v / 1000}k` : String(v))}
    />,
    <Tooltip key="tip" formatter={(_value, name, item) => {
      const key = String(item.dataKey);
      const value = item.payload?.exact_values?.[key];
      return [/pct|percent/.test(key) ? percent(value) : currency ? money(value, currency) : displayNumber(value), name];
    }} />,
    <Legend key="legend" iconType="circle" />,
  ];
  return (
    <>
    <div
      className="chart"
      style={horizontal ? { height: Math.max(290, data.length * 34 + 60) + 20 } : undefined}
      role="img"
      aria-label={`${keys.join(", ")} chart. Exact values are in the accompanying table.`}
    >
      <ResponsiveContainer width="100%" height={horizontal ? Math.max(290, data.length * 34 + 60) : 290}>
        {bar ? (
          <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"}>
            {parts}
            {keys.map((k) => (
              <Bar
                key={k}
                dataKey={k}
                name={k.replaceAll("_", " ")}
                fill={color(k)}
                radius={[4, 4, 0, 0]}
              >
                {categorical && data.map((row, index) => <Cell key={index} fill={color(String(row[x]))} />)}
              </Bar>
            ))}
          </BarChart>
        ) : (
          <LineChart data={data}>
            {parts}
            {keys.map((k) => (
              <Line
                key={k}
                dataKey={k}
                name={k.replaceAll("_", " ")}
                stroke={color(k)}
                strokeWidth={2.5}
                dot={data.length < 10}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
    <details className="chart-colors"><summary>Customize chart colors</summary>
      <div className="form-grid">{labels.map(label => <label key={label}><input type="color" aria-label={`Color for ${label}`} value={color(label)} onChange={e => setOverrides({...overrides,[label]:e.target.value})} /> {label.replaceAll("_"," ")}</label>)}</div>
      <button type="button" onClick={() => setOverrides({})}>Reset chart colors</button>
    </details>
    </>
  );
}
