import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, money } from "./api";
import { refreshedRange, type DateRange } from "./reporting-range";
import { Card, Chart, Field, Notice, Select } from "./components";
import type { Row } from "./types";
import "./appointments.css";

type AppointmentsProps = { dataVersion?: number };

export const APPOINTMENT_CSV_HEADERS = [
  "date",
  "clinic_location",
  "category",
  "appointment_count",
  "billed_amount",
  "collected_amount",
] as const;

class AppointmentCsvValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AppointmentCsvValidationError";
  }
}

const MAX_APPOINTMENT_ROWS = 5000;
const MAX_APPOINTMENT_COUNT = 2147483647;

function count(value: unknown): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "Unknown";
  return Number(value).toLocaleString("en-US");
}

function amount(value: unknown, currency = "USD"): string {
  return value === null || value === undefined ? "Unknown" : money(value, currency);
}

function percentage(value: unknown): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "Unknown";
  return `${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function dateLabel(value: unknown): string {
  if (!value) return "Unknown period";
  const text = String(value);
  const parsed = new Date(`${text}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? text
    : parsed.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      });
}

function periodStatus(row: Row): string {
  if (!row.observed) return "Unknown — no aggregate row";
  if (row.partial || row.coverage_complete === false) return "Partial coverage";
  return "Recorded coverage";
}

function labelsFromConfig(value: unknown): Record<string, string> {
  if (Array.isArray(value)) return Object.fromEntries(value.map((item) => [String(item), String(item)]));
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, label]) => typeof label === "string")
      .map(([key, label]) => [key, String(label)]),
  );
}

function mappingsFromConfig(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([, canonical]) => typeof canonical === "string")
      .map(([source, canonical]) => [source, String(canonical)]),
  );
}

function parseCsvRecords(text: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let quoted = false;
  let sawValue = false;

  const finishField = () => {
    record.push(field);
    field = "";
    sawValue = true;
  };
  const finishRecord = () => {
    if (record.length || sawValue || field) {
      finishField();
      if (record.some((value) => value.trim() !== "")) records.push(record);
    }
    record = [];
    sawValue = false;
  };

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
      continue;
    }
    if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ",") {
      finishField();
    } else if (character === "\n" || character === "\r") {
      finishRecord();
      if (character === "\r" && text[index + 1] === "\n") index += 1;
    } else {
      field += character;
    }
  }
  if (quoted) throw new AppointmentCsvValidationError("The CSV contains an unfinished quoted field.");
  if (record.length || sawValue || field) finishRecord();
  return records;
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return (
    Number.isFinite(parsed.getTime()) &&
    parsed.getUTCFullYear() === Number(value.slice(0, 4)) &&
    parsed.getUTCMonth() + 1 === Number(value.slice(5, 7)) &&
    parsed.getUTCDate() === Number(value.slice(8, 10))
  );
}

function normalizedAmount(value: string, rowNumber: number, field: string): string | null {
  const clean = value.trim();
  if (!clean) return null;
  if (!/^-?(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(clean)) {
    throw new AppointmentCsvValidationError(`CSV row ${rowNumber} has an invalid ${field}. Use a decimal amount with at most two places.`);
  }
  const whole = clean.replace("-", "").split(".")[0].replace(/^0+/, "") || "0";
  if (whole.length > 16) {
    throw new AppointmentCsvValidationError(`CSV row ${rowNumber} has an out-of-range ${field}.`);
  }
  return clean;
}

/** Parse and validate the identifier-free appointment CSV template locally. */
export function parseAppointmentCSV(text: string, config: Row): Row[] {
  const records = parseCsvRecords(text);
  if (!records.length) throw new AppointmentCsvValidationError("Choose a CSV with the approved appointment template headers.");

  const headers = records[0].map((value, index) => (index === 0 ? value.replace(/^\uFEFF/, "") : value).trim());
  const hasExactHeaders =
    headers.length === APPOINTMENT_CSV_HEADERS.length &&
    new Set(headers).size === APPOINTMENT_CSV_HEADERS.length &&
    APPOINTMENT_CSV_HEADERS.every((header) => headers.includes(header));
  if (!hasExactHeaders) {
    throw new AppointmentCsvValidationError(
      `CSV headers must be exactly ${APPOINTMENT_CSV_HEADERS.join(", ")}. Unknown columns are rejected.`,
    );
  }

  const configuredLabels = labelsFromConfig(config.category_labels);
  const labels = Object.keys(configuredLabels).length
    ? configuredLabels
    : labelsFromConfig(config.categories);
  const mappings = mappingsFromConfig(config.category_mappings);
  const clinics = new Set(Array.isArray(config.clinic_locations) ? config.clinic_locations.map(String) : []);
  if (!clinics.size) {
    throw new AppointmentCsvValidationError("No approved clinic locations are configured for appointment imports.");
  }

  const column = (name: string) => headers.indexOf(name);
  const rows = records.slice(1);
  if (!rows.length) throw new AppointmentCsvValidationError("The appointment CSV has no data rows.");
  if (rows.length > MAX_APPOINTMENT_ROWS) {
    throw new AppointmentCsvValidationError(`The appointment CSV has more than ${MAX_APPOINTMENT_ROWS.toLocaleString()} rows.`);
  }

  return rows.map((raw, index) => {
    const rowNumber = index + 2;
    if (raw.length !== headers.length) {
      throw new AppointmentCsvValidationError(`CSV row ${rowNumber} must contain exactly ${headers.length} columns.`);
    }
    const value = (name: string) => String(raw[column(name)] ?? "").trim();
    const date = value("date");
    const clinic = value("clinic_location");
    const sourceCategory = value("category");
    const countValue = value("appointment_count");
    if (!validDate(date)) throw new AppointmentCsvValidationError(`CSV row ${rowNumber} has an invalid date.`);
    if (!clinics.has(clinic)) throw new AppointmentCsvValidationError(`CSV row ${rowNumber} has an unapproved clinic location.`);

    const category = labels[sourceCategory] !== undefined
      ? sourceCategory
      : mappings[sourceCategory] && labels[mappings[sourceCategory]] !== undefined
        ? mappings[sourceCategory]
        : "";
    if (!category) throw new AppointmentCsvValidationError(`CSV row ${rowNumber} has an unapproved appointment category.`);
    if (!/^\d+$/.test(countValue) || Number(countValue) > MAX_APPOINTMENT_COUNT) {
      throw new AppointmentCsvValidationError(`CSV row ${rowNumber} appointment_count must be a nonnegative integer.`);
    }

    return {
      date,
      clinic_location: clinic,
      category,
      appointment_count: Number(countValue),
      billed_amount: normalizedAmount(value("billed_amount"), rowNumber, "billed_amount"),
      collected_amount: normalizedAmount(value("collected_amount"), rowNumber, "collected_amount"),
    };
  });
}

async function readTextFile(file: File): Promise<string> {
  const candidate = file as File & { arrayBuffer?: () => Promise<ArrayBuffer>; text?: () => Promise<string> };
  try {
    if (typeof candidate.arrayBuffer === "function") {
      return new TextDecoder("utf-8", { fatal: true }).decode(await candidate.arrayBuffer());
    }
    if (typeof candidate.text === "function") return await candidate.text();
  } catch {
    throw new AppointmentCsvValidationError("The CSV must be valid UTF-8. Nothing was uploaded.");
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(new TextDecoder("utf-8", { fatal: true }).decode(reader.result as ArrayBuffer));
      } catch {
        reject(new AppointmentCsvValidationError("The CSV must be valid UTF-8. Nothing was uploaded."));
      }
    };
    reader.onerror = () => reject(new AppointmentCsvValidationError("The CSV could not be read. Nothing was uploaded."));
    reader.readAsArrayBuffer(file);
  });
}

function safeImportError(error: unknown, fallback: string): string {
  const message = error instanceof ApiError || error instanceof AppointmentCsvValidationError ? error.message : "";
  return message && message.length <= 300 && !/[\r\n\0]/.test(message) ? message : fallback;
}

function coverageLabel(coverage: unknown): string {
  if (!coverage || typeof coverage !== "object") return "Coverage unavailable";
  const item = coverage as Record<string, unknown>;
  const known = Number(item.known_rows || 0);
  const total = Number(item.total_rows || 0);
  if (!total) return "No recorded amounts";
  if (known === total) return `Recorded for ${total.toLocaleString("en-US")} row${total === 1 ? "" : "s"}`;
  if (!known) return `Unknown for ${total.toLocaleString("en-US")} rows`;
  return `Partial: ${known.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} rows recorded`;
}

function coverageShort(coverage: unknown): string {
  if (!coverage || typeof coverage !== "object") return "Unknown";
  const item = coverage as Record<string, unknown>;
  const known = Number(item.known_rows || 0);
  const total = Number(item.total_rows || 0);
  if (!total || !known) return "Unknown";
  return known === total ? "Recorded" : "Partial";
}

function categoryObserved(row: Row): boolean {
  if (row.observed === true || Number(row.row_count) > 0) return true;
  return Number(row.billed_coverage?.total_rows || 0) > 0 || Number(row.collected_coverage?.total_rows || 0) > 0;
}

function periodRange(metadata: Row | null): DateRange {
  const today = new Date().toISOString().slice(0, 10);
  const start = String(metadata?.first_date || today);
  const end = String(metadata?.last_date || today);
  return start <= end ? { start, end } : { start: today, end: today };
}

function useAppointmentConfig(dataVersion: number) {
  const [config, setConfig] = useState<Row | null>(null);
  const [metadata, setMetadata] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [nextConfig, nextMetadata] = await Promise.all([
        api<Row>("/appointments/config"),
        api<Row>("/appointments/metadata"),
      ]);
      setConfig(nextConfig);
      setMetadata(nextMetadata);
      return nextMetadata;
    } catch (cause) {
      setError((cause as Error).message || "Appointment activity could not be loaded.");
      throw cause;
    }
  }, []);

  useEffect(() => {
    const refreshOnDataChange = () => setRevision((value) => value + 1);
    window.addEventListener("clinic-data-updated", refreshOnDataChange);
    return () => window.removeEventListener("clinic-data-updated", refreshOnDataChange);
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [dataVersion, revision, refresh]);

  return { config, metadata, error, refresh };
}

function templateCSV(): string {
  return [
    APPOINTMENT_CSV_HEADERS.join(","),
    "2026-09-07,North,new_patient,8,960.00,720.00",
    "2026-09-07,North,follow_up,12,840.00,",
    "2026-09-08,North,new_patient,0,0.00,0.00",
  ].join("\n") + "\n";
}

function downloadTemplate() {
  const createUrl = window.URL?.createObjectURL;
  if (!createUrl) return;
  const url = createUrl.call(window.URL, new Blob([templateCSV()], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "appointment-activity-template.csv";
  link.click();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

export default function Appointments({ dataVersion = 0 }: AppointmentsProps) {
  const { config, metadata, error, refresh } = useAppointmentConfig(dataVersion);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [frequency, setFrequency] = useState("week");
  const [clinic, setClinic] = useState("");
  const [category, setCategory] = useState("");
  const [report, setReport] = useState<Row | null>(null);
  const [reportError, setReportError] = useState("");
  const [reportVersion, setReportVersion] = useState(0);
  const availableRange = useRef<DateRange | null>(null);
  const currentRange = useRef<DateRange>({ start: "", end: "" });
  currentRange.current = { start, end };

  const categoryLabels = useMemo(() => {
    const configured = labelsFromConfig(config?.category_labels);
    return Object.keys(configured).length ? configured : labelsFromConfig(config?.categories);
  }, [config]);
  const configuredClinics = Array.isArray(config?.clinic_locations)
    ? config.clinic_locations.map(String)
    : [];
  const observedClinics = Array.isArray(metadata?.clinic_locations)
    ? metadata.clinic_locations.map(String)
    : [];
  const clinics = Array.from(new Set([...configuredClinics, ...observedClinics]));
  const categories = Object.keys(categoryLabels).length
    ? Object.keys(categoryLabels)
    : Array.isArray(metadata?.categories)
      ? metadata.categories.map(String)
      : [];
  const canRead = Boolean(config?.read_enabled ?? config?.enabled);

  useEffect(() => {
    if (!metadata) return;
    const next = periodRange(metadata);
    if (!availableRange.current) availableRange.current = next;
    setStart((value) => value || next.start);
    setEnd((value) => value || next.end);
  }, [metadata]);

  useEffect(() => {
    if (!canRead || !start || !end) return;
    let active = true;
    setReport(null);
    setReportError("");
    const query = new URLSearchParams({ start, end, frequency });
    if (clinic) query.set("clinic_location", clinic);
    if (category) query.set("category", category);
    api<Row>(`/appointments/report?${query.toString()}`)
      .then((value) => active && setReport(value))
      .catch((cause: unknown) => active && setReportError((cause as Error).message));
    return () => {
      active = false;
    };
  }, [canRead, start, end, frequency, clinic, category, reportVersion]);


  if (error) return <Notice error>{error}</Notice>;
  if (!config || !metadata) return <Notice>Loading appointment activity…</Notice>;
  if (!canRead) {
    return (
      <Card title="Appointment activity access not configured">
        <p>Your administrator needs to enable analytics access for this view.</p>
      </Card>
    );
  }

  const summary = report?.summary || {};
  const comparison = report?.comparison || {};
  const periods: Row[] = Array.isArray(report?.periods) ? report.periods : [];
  const categoryRows: Row[] = Array.isArray(report?.categories) ? report.categories : [];
  const locationRows: Row[] = Array.isArray(report?.locations) ? report.locations : [];
  // The configured clinic currency is authoritative for appointment amounts.
  const currency = String(config.currency || report?.currency || "USD");
  const chartPeriods = periods.map((row) => ({
    ...row,
    appointment_count: row.observed ? row.appointment_count : null,
  }));
  const chartCategories = categoryRows.map((row) => ({
    ...row,
    label: row.label || categoryLabels[row.category] || row.category,
    appointment_count: categoryObserved(row) ? row.appointment_count : null,
  }));
  const summaryObserved = Boolean(summary.observed);

  return (
    <div className="appointments-view">
      <Notice>
        This view reports aggregate appointment volume. It does not count unique patients, and it never derives appointments from financial rows.
      </Notice>
      <div className="appointments-controls">
        <Field label="From" type="date" value={start} onChange={setStart} />
        <Field label="Through" type="date" value={end} onChange={setEnd} />
        <Select
          label="Period"
          value={frequency}
          onChange={setFrequency}
          options={[["week", "Weekly"], ["month", "Monthly"], ["quarter", "Quarterly"]]}
        />
        <Select
          label="Clinic location"
          value={clinic}
          onChange={setClinic}
          options={[["", "All clinics"], ...clinics.map((value) => [value, value] as [string, string])]}
        />
        <Select
          label="Appointment category"
          value={category}
          onChange={setCategory}
          options={[["", "All categories"], ...categories.map((value) => [value, categoryLabels[value] || value] as [string, string])]}
        />
      </div>
      {reportError && <Notice error>{reportError}</Notice>}
      {!report ? (
        !reportError && <Notice>Loading the selected appointment range…</Notice>
      ) : (
        <>
          <div className="appointment-metrics">
            <div className="metric">
              <span>Appointments</span>
              <strong>{summaryObserved ? count(summary.appointment_count) : "Unknown"}</strong>
              <small>{summaryObserved ? "Explicit aggregate count" : "No aggregate row recorded"}</small>
            </div>
            <div className="metric">
              <span>Prior matched period</span>
              <strong>{count(comparison.appointment_count)}</strong>
              <small>{comparison.status === "complete" ? "Complete comparison" : "Partial or unavailable comparison"}</small>
            </div>
            <div className="metric">
              <span>Billed amount</span>
              <strong>{amount(summary.billed_amount, currency)}</strong>
              <small>{coverageLabel(summary.billed_coverage)}</small>
            </div>
            <div className="metric">
              <span>Collected amount</span>
              <strong>{amount(summary.collected_amount, currency)}</strong>
              <small>{coverageLabel(summary.collected_coverage)}</small>
            </div>
            <div className="metric">
              <span>Average billed / appointment</span>
              <strong>{amount(summary.average_billed_amount, currency)}</strong>
              <small>{summary.average_billed_amount == null ? "Requires complete billed coverage" : "Two decimal places"}</small>
            </div>
            <div className="metric">
              <span>Average collected / appointment</span>
              <strong>{amount(summary.average_collected_amount, currency)}</strong>
              <small>{summary.average_collected_amount == null ? "Requires complete collected coverage" : "Two decimal places"}</small>
            </div>
          </div>
          <div className="two-col equal">
            <Card title="Appointments by category">
              <p className="muted">Counts supplied by the approved aggregate source. Unobserved categories remain unknown.</p>
              <Chart bar horizontal x="label" rows={chartCategories} keys={["appointment_count"]} />
            </Card>
            <Card title="Matched prior period">
              <div className="appointment-comparison">
                <strong>{comparison.change == null ? "Unknown" : `${Number(comparison.change) > 0 ? "+" : ""}${count(comparison.change)}`}</strong>
                <span>{percentage(comparison.change_pct)}</span>
                <small>
                  {comparison.period_start ? `${dateLabel(comparison.period_start)} to ${dateLabel(comparison.period_end)}` : "No prior period available"}
                </small>
              </div>
              <p className="muted">A change is shown only when both selected ranges have explicit daily coverage.</p>
            </Card>
          </div>
          <Card title="Activity trend">
            <Chart rows={chartPeriods} keys={["appointment_count"]} />
            <div className="table-scroll">
              <table>
                <thead><tr><th>Period</th><th>Appointments</th><th>Billed amount</th><th>Collected amount</th><th>Coverage</th></tr></thead>
                <tbody>
                  {periods.length ? periods.map((row, index) => (
                    <tr key={`${row.period_start}-${index}`}>
                      <td>{dateLabel(row.period_start)} to {dateLabel(row.period_end)}</td>
                      <td>{row.observed ? count(row.appointment_count) : "Unknown"}</td>
                      <td>{amount(row.billed_amount, currency)} <small className="table-note">{coverageShort(row.billed_coverage)}</small></td>
                      <td>{amount(row.collected_amount, currency)} <small className="table-note">{coverageShort(row.collected_coverage)}</small></td>
                      <td>{periodStatus(row)}</td>
                    </tr>
                  )) : <tr><td colSpan={5}>No aggregate rows in this range.</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="two-col equal">
            <Card title="Category totals">
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Category</th><th>Appointments</th><th>Billed amount</th><th>Collected amount</th></tr></thead>
                  <tbody>{categoryRows.map((row) => <tr key={String(row.category)}><td>{row.label || categoryLabels[row.category] || row.category}</td><td>{categoryObserved(row) ? count(row.appointment_count) : "Unknown"}</td><td>{amount(row.billed_amount, currency)} <small className="table-note">{coverageShort(row.billed_coverage)}</small></td><td>{amount(row.collected_amount, currency)} <small className="table-note">{coverageShort(row.collected_coverage)}</small></td></tr>)}</tbody>
                </table>
              </div>
            </Card>
            <Card title="Clinic totals">
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Clinic location</th><th>Appointments</th></tr></thead>
                  <tbody>{locationRows.map((row) => <tr key={String(row.clinic_location)}><td>{row.clinic_location}</td><td>{count(row.appointment_count)}</td></tr>)}</tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

export { dateLabel, periodStatus, coverageLabel, percentage };
