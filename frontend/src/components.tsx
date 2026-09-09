import type { ReactNode } from "react";
import { lazy, Suspense } from "react";
import { money } from "./api";
import type { Row } from "./types";
const Plot = lazy(() => import("./plots"));
export function Chart(props: {
  rows: Row[];
  keys: string[];
  x?: string;
  bar?: boolean;
}) {
  return (
    <Suspense fallback={<p role="status">Loading chart…</p>}>
      <Plot {...props} />
    </Suspense>
  );
}
export function Card({
  title,
  children,
  action,
}: {
  title?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="card">
      {title && (
        <div className="card-heading">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Field({
  label,
  value,
  onChange,
  type = "text",
  min,
  max,
  required = false,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  type?: string;
  min?: number;
  max?: number;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        required={required}
        type={type}
        min={min}
        max={max}
        step={type === "number" ? "any" : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: (string | [string, string])[];
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => {
          const [v, l] = typeof o === "string" ? [o, o] : o;
          return (
            <option key={v} value={v}>
              {l}
            </option>
          );
        })}
      </select>
    </label>
  );
}
export function Notice({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      className={error ? "notice error" : "notice"}
      role={error ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
export function Metrics({
  items,
  currency = "USD",
}: {
  items: [string, unknown, string?][];
  currency?: string;
}) {
  return (
    <div className="metrics">
      {items.map(([label, value, note]) => (
        <div className="metric" key={label}>
          <span>{label}</span>
          <strong>
            {label.includes("%")
              ? value == null
                ? "No data"
                : `${value}%`
              : money(value, currency)}
          </strong>
          {note && <small>{note}</small>}
        </div>
      ))}
    </div>
  );
}
export function Table({ rows, columns }: { rows: Row[]; columns?: string[] }) {
  const cols = columns || Object.keys(rows[0] || {});
  return rows.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c.replaceAll("_", " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c}>
                  {r[c] === null || r[c] === undefined
                    ? "—"
                    : typeof r[c] === "object"
                      ? JSON.stringify(r[c])
                      : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="empty">No records in this view yet.</p>
  );
}
export function Evidence({
  value,
  label = "Full assumptions",
}: {
  value: unknown;
  label?: string;
}) {
  return (
    <details className="evidence">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
