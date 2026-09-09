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
const colors = ["#167b70", "#df9462", "#6d77b5", "#a46885"];
export default function Plot({
  rows,
  keys,
  x = "period_start",
  bar = false,
}: {
  rows: Row[];
  keys: string[];
  x?: string;
  bar?: boolean;
}) {
  const data = rows.map((r) => ({
    ...r,
    ...Object.fromEntries(
      keys.map((k) => [k, r[k] == null ? null : Number(r[k])]),
    ),
  }));
  const parts = [
    <CartesianGrid key="grid" vertical={false} stroke="#e9eeeb" />,
    <XAxis
      key="x"
      dataKey={x}
      tickLine={false}
      axisLine={false}
      tick={{ fontSize: 11, fill: "#62736e" }}
      minTickGap={25}
    />,
    <YAxis
      key="y"
      width={65}
      tickLine={false}
      axisLine={false}
      tick={{ fontSize: 11, fill: "#62736e" }}
      tickFormatter={(v) => (Math.abs(v) >= 1000 ? `${v / 1000}k` : String(v))}
    />,
    <Tooltip key="tip" />,
    <Legend key="legend" iconType="circle" />,
  ];
  return (
    <div
      className="chart"
      role="img"
      aria-label={`${keys.join(", ")} chart. Exact values are in the accompanying table.`}
    >
      <ResponsiveContainer width="100%" height={290}>
        {bar ? (
          <BarChart data={data}>
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
