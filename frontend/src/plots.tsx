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
} from "recharts";
import type { Row } from "./types";
import { money } from "./api";
const colors = ["#167b70", "#df9462", "#6d77b5", "#a46885"];
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
  const data = rows.map((r) => ({
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
    <Tooltip key="tip" formatter={currency ? ((_value, name, item) => [money(item.payload?.exact_values?.[String(item.dataKey)], currency), name]) : undefined} />,
    <Legend key="legend" iconType="circle" />,
  ];
  return (
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
            {keys.map((k, i) => (
              <Bar
                key={k}
                dataKey={k}
                name={k.replaceAll("_", " ")}
                fill={colors[i % 4]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        ) : (
          <LineChart data={data}>
            {parts}
            {keys.map((k, i) => (
              <Line
                key={k}
                dataKey={k}
                name={k.replaceAll("_", " ")}
                stroke={colors[i % 4]}
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
  );
}
